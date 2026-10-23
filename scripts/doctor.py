#!/usr/bin/env python3
"""Check that everything TikTok Hooks needs is installed, and say how to fix gaps.

Runs with any Python 3, before or after install.sh, so setup can start here.
"""

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
SKILL_DIR = HOME / ".claude" / "skills" / "tiktok-hooks"
VENV_PYTHON = HOME / ".local" / "share" / "tiktok-hooks" / "venv" / "bin" / "python"
WHISPER_CACHE = HOME / ".cache" / "whisper"
CONFIG_PATH = HOME / ".config" / "tiktok-hooks" / "config.json"
BREW_PATHS = ("/opt/homebrew/bin/brew", "/usr/local/bin/brew")
FFMPEG_PATHS = ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg")
INSTALL = (
    "git clone https://github.com/louisedesadeleer/tiktok-hooks.git && "
    "cd tiktok-hooks && bash install.sh"
)
BREW_INSTALL = (
    '/bin/bash -c "$(curl -fsSL '
    'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
)


def find(name: str, fallbacks: tuple[str, ...]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    return next((path for path in fallbacks if Path(path).exists()), None)


def venv_has(*modules: str) -> list[str]:
    if not VENV_PYTHON.exists():
        return list(modules)
    missing = []
    for module in modules:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", f"import {module}"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            missing.append(module)
    return missing


def checks() -> list[dict]:
    results = []

    def add(name, ok, detail, fix=None, required=True):
        results.append(
            {"name": name, "ok": ok, "detail": detail, "fix": fix, "required": required}
        )

    is_mac = platform.system() == "Darwin"
    add("macOS", is_mac, platform.system(), "TikTok Hooks runs on macOS only.")

    version = sys.version_info
    add(
        "Python 3.10+",
        version >= (3, 10),
        f"{version.major}.{version.minor}",
        "Install a newer Python: brew install python",
    )

    brew = find("brew", BREW_PATHS)
    ffmpeg = find("ffmpeg", FFMPEG_PATHS)
    # Homebrew only matters as the way to get ffmpeg.
    add(
        "Homebrew",
        bool(brew),
        brew or "not found",
        f"Install Homebrew: {BREW_INSTALL}",
        required=not ffmpeg,
    )
    add(
        "ffmpeg",
        bool(ffmpeg),
        ffmpeg or "not found",
        "Install ffmpeg: brew install ffmpeg",
    )

    skill = (SKILL_DIR / "SKILL.md").exists()
    add("Skill files", skill, str(SKILL_DIR), f"Install the skill: {INSTALL}")

    missing = venv_has("whisper", "yt_dlp")
    add(
        "Whisper + yt-dlp",
        not missing,
        str(VENV_PYTHON) if not missing else "missing: " + ", ".join(missing),
        f"Install or repair the skill environment: {INSTALL}",
    )

    models = sorted(path.stem for path in WHISPER_CACHE.glob("*.pt"))
    add(
        "Whisper model",
        bool(models),
        ", ".join(models) if models else "downloads on first sync (~140 MB)",
        required=False,
    )

    add(
        "Configuration",
        CONFIG_PATH.exists(),
        str(CONFIG_PATH) if CONFIG_PATH.exists() else "not set up yet",
        "Ask Claude to set up the TikTok hooks skill.",
        required=False,
    )
    return results


def main() -> None:
    results = checks()
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        for item in results:
            mark = "✓" if item["ok"] else ("✗" if item["required"] else "–")
            print(f"{mark} {item['name']}: {item['detail']}")
            if not item["ok"] and item["fix"] and item["required"]:
                print(f"    → {item['fix']}")
    if any(not item["ok"] and item["required"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
