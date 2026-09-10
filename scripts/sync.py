#!/usr/bin/env python3
"""Download unseen TikToks, extract their openings, and save them to Markdown."""

import argparse
import fcntl
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from hooks import extract_hook, markdown_entry

CONFIG_DIR = Path(
    os.environ.get("TIKTOK_HOOKS_CONFIG_HOME", Path.home() / ".config" / "tiktok-hooks")
)
DATA_DIR = Path(
    os.environ.get(
        "TIKTOK_HOOKS_DATA_HOME", Path.home() / ".local" / "share" / "tiktok-hooks"
    )
)
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = DATA_DIR / "seen.json"
LOCK_PATH = DATA_DIR / "sync.lock"
MAX_TRANSCRIPT_SECONDS = 60


class SyncError(RuntimeError):
    pass


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback

    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise SyncError(f"Invalid JSON at {path}: {error}") from error


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_config() -> dict:
    config = load_json(CONFIG_PATH, {})
    if not config.get("markdown_path"):
        raise SyncError(
            f"No configuration found. Run scripts/configure.py before syncing ({CONFIG_PATH})."
        )
    return config


def markdown_video_ids(markdown: Path) -> set[str]:
    if not markdown.exists():
        return set()

    return set(
        re.findall(r"^- TikTok ID: `([^`]+)`$", markdown.read_text(), re.MULTILINE)
    )


def load_state(markdown: Path) -> dict:
    state = load_json(
        STATE_PATH, {"saved": [], "skipped": [], "collection_initialized": False}
    )
    if isinstance(state, list):
        state = {"seen": state, "collection_initialized": True}
    if not isinstance(state, dict):
        state = {"saved": [], "skipped": [], "collection_initialized": False}

    state.setdefault("collection_initialized", False)
    if "saved" not in state:
        legacy_seen = set(state.pop("seen", []))
        state["saved"] = sorted(legacy_seen & markdown_video_ids(markdown))
        state["skipped"] = sorted(legacy_seen - set(state["saved"]))
    state.setdefault("skipped", [])
    return state


@contextmanager
def sync_lock():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SyncError("Another TikTok Hooks sync is already running.") from error

        yield


def run(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise SyncError(f"Command timed out: {command[0]}") from error


def yt_dlp_command(config: dict) -> list[str]:
    command = [sys.executable, "-m", "yt_dlp"]
    if config.get("browser"):
        command.extend(["--cookies-from-browser", config["browser"]])
    return command


def find_ffmpeg() -> str:
    candidates = [
        shutil.which("ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate

    raise SyncError(
        "ffmpeg is required. On macOS, install it with: brew install ffmpeg"
    )


def check_downloader() -> None:
    if importlib.util.find_spec("yt_dlp") is None:
        raise SyncError("yt-dlp is missing from this Python environment.")


def check_dependencies() -> str:
    check_downloader()
    if importlib.util.find_spec("whisper") is None:
        raise SyncError("openai-whisper is missing from this Python environment.")
    return find_ffmpeg()


def video_from_entry(entry: dict) -> dict | None:
    if not entry or not entry.get("id"):
        return None

    video_id = str(entry["id"])
    url = entry.get("webpage_url") or entry.get("url") or ""
    if not str(url).startswith("http"):
        url = f"https://www.tiktok.com/@_/video/{video_id}"

    return {
        "id": video_id,
        "title": " ".join((entry.get("title") or "").split()) or "Untitled TikTok",
        "uploader": entry.get("uploader") or entry.get("channel") or "unknown",
        "url": url,
    }


def list_collection(config: dict) -> list[dict]:
    if not config.get("collection_url"):
        raise SyncError("No collection is configured. Provide a TikTok URL with --url.")

    command = yt_dlp_command(config)
    command.extend(
        [
            "--flat-playlist",
            "--playlist-items",
            f"1:{config.get('check_count', 30)}",
            "--dump-single-json",
            config["collection_url"],
        ]
    )
    result = run(command, timeout=120)
    if result.returncode != 0:
        raise SyncError(f"Could not list the collection:\n{result.stderr[-800:]}")

    data = json.loads(result.stdout)
    videos = [video_from_entry(entry) for entry in data.get("entries") or []]
    return [video for video in videos if video]


def inspect_url(url: str, config: dict) -> dict:
    command = yt_dlp_command(config)
    command.extend(["--no-playlist", "--skip-download", "--dump-single-json", url])
    result = run(command, timeout=120)
    if result.returncode != 0:
        raise SyncError(f"Could not read that TikTok:\n{result.stderr[-800:]}")

    video = video_from_entry(json.loads(result.stdout))
    if not video:
        raise SyncError("TikTok returned no video metadata.")
    return video


def download_video(video: dict, config: dict, destination: Path) -> Path:
    output = destination / "video.%(ext)s"
    command = yt_dlp_command(config)
    command.extend(
        [
            "--no-playlist",
            "--format",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "--output",
            str(output),
            video["url"],
        ]
    )
    result = run(command)
    media = destination / "video.mp4"
    if result.returncode != 0 or not media.exists():
        raise SyncError(f"Download failed:\n{result.stderr[-600:]}")
    return media


def extract_media(ffmpeg: str, media: Path, frame: Path, audio: Path) -> None:
    frame_result = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame),
        ]
    )
    if frame_result.returncode != 0 or not frame.exists():
        raise SyncError(f"First-frame extraction failed:\n{frame_result.stderr[-400:]}")

    audio_result = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media),
            "-t",
            str(MAX_TRANSCRIPT_SECONDS),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio),
        ]
    )
    if audio_result.returncode != 0 or not audio.exists():
        raise SyncError(f"Audio extraction failed:\n{audio_result.stderr[-400:]}")


def process_video(
    video: dict,
    config: dict,
    model,
    ffmpeg: str,
    workdir: Path,
) -> dict:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", video["id"])
    if not safe_id:
        raise SyncError("TikTok returned an invalid video ID.")

    destination = workdir / safe_id
    destination.mkdir(parents=True, exist_ok=True)
    media = download_video(video, config, destination)
    assets = Path(config["assets_path"]).expanduser()
    assets.mkdir(parents=True, exist_ok=True)
    frame = assets / f"{safe_id}.jpg"
    extracted_frame = destination / "opening.jpg"
    staged_frame = frame.with_suffix(frame.suffix + ".tmp")
    audio = destination / "opening.wav"

    extract_media(ffmpeg, media, extracted_frame, audio)
    transcript = model.transcribe(str(audio), fp16=False)
    hook = extract_hook(transcript["text"])
    try:
        shutil.copyfile(extracted_frame, staged_frame)
        staged_frame.replace(frame)
    finally:
        staged_frame.unlink(missing_ok=True)

    video.update(
        {
            "hook": hook,
            "frame_path": str(frame.resolve()),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return video


def append_markdown(markdown: Path, videos: list[dict]) -> None:
    markdown.parent.mkdir(parents=True, exist_ok=True)
    existing = markdown.read_text() if markdown.exists() else "# TikTok Hooks\n\n"
    block = "".join(markdown_entry(video, markdown) for video in videos)

    if existing.startswith("# ") and "\n\n" in existing:
        heading, _, rest = existing.partition("\n\n")
        updated = f"{heading}\n\n{block}{rest}"
    else:
        updated = block + existing

    temporary = markdown.with_suffix(markdown.suffix + ".tmp")
    temporary.write_text(updated)
    temporary.replace(markdown)


def select_collection_videos(
    videos: list[dict], state: dict, config: dict
) -> list[dict]:
    saved = set(state["saved"])
    skipped = set(state.get("skipped", []))
    unseen = [video for video in videos if video["id"] not in saved | skipped]
    if state["collection_initialized"]:
        return unseen

    initial_count = config.get("initial_import_count", 5)
    selected = unseen[:initial_count]
    selected_ids = {video["id"] for video in selected}
    skipped.update(video["id"] for video in videos if video["id"] not in selected_ids)
    state["skipped"] = sorted(skipped)
    state["collection_initialized"] = True
    return selected


def sync(arguments: argparse.Namespace) -> tuple[list[dict], list[tuple[dict, str]]]:
    config = load_config()
    markdown = Path(config["markdown_path"]).expanduser()
    state = load_state(markdown)
    saved = set(state["saved"])
    check_downloader()

    if arguments.url:
        candidates = [inspect_url(arguments.url, config)]
    else:
        candidates = select_collection_videos(list_collection(config), state, config)

    if not arguments.force:
        candidates = [video for video in candidates if video["id"] not in saved]
    if not candidates:
        write_json(STATE_PATH, state)
        return [], []

    ffmpeg = check_dependencies()
    import whisper

    model = whisper.load_model(config.get("whisper_model", "base"))
    completed = []
    failed = []
    with tempfile.TemporaryDirectory(prefix="tiktok-hooks-") as temporary:
        workdir = Path(temporary)
        for video in candidates:
            print(f"Processing @{video['uploader']}: {video['title'][:70]}")
            try:
                completed.append(process_video(video, config, model, ffmpeg, workdir))
            except Exception as error:  # noqa: BLE001
                failed.append((video, str(error)))
                print(f"warning: {video['id']} failed: {error}", file=sys.stderr)

    if completed:
        append_markdown(markdown, completed)
        saved.update(video["id"] for video in completed)

    state["saved"] = sorted(saved | set(state["saved"]))
    state["skipped"] = sorted(set(state["skipped"]) - set(state["saved"]))
    write_json(STATE_PATH, state)
    return completed, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Save TikTok hooks to local Markdown.")
    parser.add_argument(
        "--url", help="save one TikTok instead of syncing the collection"
    )
    parser.add_argument(
        "--force", action="store_true", help="process an already-seen video"
    )
    arguments = parser.parse_args()

    try:
        with sync_lock():
            completed, failed = sync(arguments)
    except SyncError as error:
        sys.exit(f"error: {error}")

    config = load_config()
    if completed:
        print(f"Saved {len(completed)} hook(s) to {config['markdown_path']}")
    elif not failed:
        print(f"No new hooks. Markdown: {config['markdown_path']}")

    if failed:
        print(f"{len(failed)} video(s) failed and will be retried.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
