"""Pure helpers for extracting and formatting TikTok hooks."""

import os
import re
from datetime import datetime
from pathlib import Path

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
MAX_SENTENCES = 3
MIN_WORDS = 12


def extract_hook(transcript: str) -> str:
    text = " ".join(transcript.split())
    if not text:
        return "No speech detected."

    sentences = SENTENCE_END.split(text)
    hook = sentences[:2]
    if len(sentences) > 2 and len(" ".join(hook).split()) < MIN_WORDS:
        hook = sentences[:MAX_SENTENCES]

    return " ".join(hook).strip()


def clean_inline(value: str, fallback: str) -> str:
    cleaned = " ".join((value or "").split()).strip()
    return cleaned or fallback


def markdown_entry(video: dict, markdown_path: Path) -> str:
    frame = Path(video["frame_path"])
    relative_frame = Path(os.path.relpath(frame, markdown_path.parent)).as_posix()
    title = clean_inline(video.get("title", ""), "Untitled TikTok")
    creator = clean_inline(video.get("uploader", ""), "unknown")
    hook = clean_inline(video.get("hook", ""), "No speech detected.")
    saved = datetime.fromisoformat(video["saved_at"]).astimezone().date().isoformat()

    return (
        f"## {title}\n\n"
        f"![Opening frame](<{relative_frame}>)\n\n"
        f"> {hook}\n\n"
        f"- Creator: @{creator.lstrip('@')}\n"
        f"- Source: <{video['url']}>\n"
        f"- Saved: {saved}\n"
        f"- TikTok ID: `{video['id']}`\n\n"
    )
