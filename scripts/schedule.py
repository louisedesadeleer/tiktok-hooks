#!/usr/bin/env python3
"""Install or remove the macOS launchd job for TikTok Hooks."""

import argparse
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.hookline.tiktok-hooks"
DATA_DIR = Path.home() / ".local" / "share" / "tiktok-hooks"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SYNC_SCRIPT = Path(__file__).resolve().parent / "sync.py"


def hour_value(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 23:
        raise argparse.ArgumentTypeError("must be between 0 and 23")
    return number


def minute_value(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 59:
        raise argparse.ArgumentTypeError("must be between 0 and 59")
    return number


def python_path() -> Path:
    installed = DATA_DIR / "venv" / "bin" / "python"
    return installed if installed.exists() else Path(sys.executable)


def plist(hour: int, minute: int) -> dict:
    logs = DATA_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python_path()), str(SYNC_SCRIPT)],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(logs / "sync.log"),
        "StandardErrorPath": str(logs / "sync.log"),
        "ProcessType": "Background",
    }


def launchctl(*arguments: str, required: bool = True) -> None:
    result = subprocess.run(
        ["launchctl", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if required and result.returncode != 0:
        sys.exit(result.stderr.strip() or "launchctl failed")


def remove() -> None:
    domain = f"gui/{os.getuid()}"
    launchctl("bootout", domain, str(PLIST_PATH), required=False)
    PLIST_PATH.unlink(missing_ok=True)
    print("Removed the daily TikTok Hooks sync.")


def install(hour: int, minute: int) -> None:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as file:
        plistlib.dump(plist(hour, minute), file)

    domain = f"gui/{os.getuid()}"
    launchctl("bootout", domain, str(PLIST_PATH), required=False)
    launchctl("bootstrap", domain, str(PLIST_PATH))
    print(f"Scheduled TikTok Hooks for {hour:02d}:{minute:02d} each day.")
    print(f"Logs: {DATA_DIR / 'logs' / 'sync.log'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule TikTok Hooks on macOS.")
    parser.add_argument("--hour", type=hour_value, default=9)
    parser.add_argument("--minute", type=minute_value, default=0)
    parser.add_argument("--remove", action="store_true")
    arguments = parser.parse_args()

    if platform.system() != "Darwin":
        sys.exit("Automatic scheduling currently supports macOS only.")

    if arguments.remove:
        remove()
    else:
        install(arguments.hour, arguments.minute)


if __name__ == "__main__":
    main()
