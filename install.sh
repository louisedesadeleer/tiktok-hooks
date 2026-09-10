#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SOURCE_DIR=""
if [[ -n "$SCRIPT_PATH" ]]; then
  SOURCE_DIR="$(cd "$(dirname "$SCRIPT_PATH")" 2>/dev/null && pwd || true)"
fi
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
TARGET_DIR="$SKILLS_DIR/tiktok-hooks"
DATA_DIR="$HOME/.local/share/tiktok-hooks"
VENV_DIR="$DATA_DIR/venv"
BASE_URL="${TIKTOK_HOOKS_BASE_URL:-https://raw.githubusercontent.com/louisedesadeleer/tiktok-hooks/v1.0.0}"

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("TikTok Hooks requires Python 3.10 or newer.")
PY

if [[ -f "$SOURCE_DIR/SKILL.md" ]]; then
  if [[ "$SOURCE_DIR" != "$TARGET_DIR" ]]; then
    rm -rf "$TARGET_DIR"
    mkdir -p "$TARGET_DIR"
    cp -R "$SOURCE_DIR"/. "$TARGET_DIR"/
  fi
else
  command -v curl >/dev/null 2>&1 || {
    printf 'curl is required to install TikTok Hooks.\n' >&2
    exit 1
  }
  rm -rf "$TARGET_DIR"
  mkdir -p "$TARGET_DIR/scripts"
  for file in SKILL.md README.md requirements.txt scripts/configure.py scripts/hooks.py scripts/schedule.py scripts/sync.py; do
    curl -fsSL "$BASE_URL/$file" -o "$TARGET_DIR/$file"
  done
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$TARGET_DIR/requirements.txt"

printf '\nInstalled TikTok Hooks at %s\n' "$TARGET_DIR"
printf 'Next: ask Claude to “Set up my TikTok hooks skill.”\n'

if ! command -v ffmpeg >/dev/null 2>&1; then
  printf '\nffmpeg is still required. On macOS, install it with: brew install ffmpeg\n'
fi
