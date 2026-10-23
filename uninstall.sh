#!/usr/bin/env bash
# Remove TikTok Hooks from this Mac: daily job, skill files, Python environment,
# configuration, Notion token, sync state, and the Whisper model cache.
# Saved hooks (your Markdown/Obsidian notes and Notion pages) are left alone.
set -euo pipefail

YES=0
KEEP_MODEL=0
for argument in "$@"; do
  case "$argument" in
    -y|--yes) YES=1 ;;
    --keep-whisper-model) KEEP_MODEL=1 ;;
    *) printf 'Usage: bash uninstall.sh [--yes] [--keep-whisper-model]\n' >&2; exit 2 ;;
  esac
done

SKILL_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}/tiktok-hooks"
DATA_DIR="$HOME/.local/share/tiktok-hooks"
CONFIG_DIR="$HOME/.config/tiktok-hooks"
WHISPER_CACHE="$HOME/.cache/whisper"
LABEL="com.hookline.tiktok-hooks"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Note where hooks were saved before the configuration is removed.
SAVED_TO=""
if [[ -f "$CONFIG_DIR/config.json" ]]; then
  SAVED_TO="$(python3 - "$CONFIG_DIR/config.json" <<'PY' 2>/dev/null || true
import json, sys
config = json.load(open(sys.argv[1]))
if config.get("notion_database_id"):
    print("Notion database " + config["notion_database_id"])
elif config.get("destination") == "notion":
    print("Notion page " + str(config.get("notion_page_id")))
elif config.get("markdown_path"):
    print(config["markdown_path"])
PY
)"
fi

targets=()
[[ -f "$PLIST" ]] && targets+=("$PLIST (daily sync)")
[[ -d "$SKILL_DIR" ]] && targets+=("$SKILL_DIR")
[[ -d "$DATA_DIR" ]] && targets+=("$DATA_DIR (Python env, Whisper, yt-dlp, sync state)")
[[ -d "$CONFIG_DIR" ]] && targets+=("$CONFIG_DIR (configuration and Notion token)")
if [[ $KEEP_MODEL -eq 0 && -d "$WHISPER_CACHE" ]]; then
  targets+=("$WHISPER_CACHE (Whisper models; shared with other Whisper tools)")
fi

if [[ ${#targets[@]} -eq 0 ]]; then
  printf 'TikTok Hooks is not installed on this Mac.\n'
  exit 0
fi

printf 'This removes:\n'
printf '  • %s\n' "${targets[@]}"
if [[ $YES -eq 0 ]]; then
  read -r -p "Continue? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { printf 'Nothing removed.\n'; exit 0; }
fi

if [[ -f "$PLIST" ]]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
fi
rm -rf "$SKILL_DIR" "$DATA_DIR" "$CONFIG_DIR"
[[ $KEEP_MODEL -eq 0 ]] && rm -rf "$WHISPER_CACHE"

printf '\nTikTok Hooks is uninstalled.\n'
if [[ -n "$SAVED_TO" ]]; then
  printf 'Your saved hooks were left in place: %s\n' "$SAVED_TO"
fi
printf 'To finish a clean slate:\n'
printf '  • Delete the Notion connection at https://www.notion.so/profile/integrations (if you made one)\n'
printf '  • ffmpeg and Homebrew were kept; remove ffmpeg with: brew uninstall ffmpeg\n'
printf '  • Delete this checkout folder if you cloned the repo\n'
