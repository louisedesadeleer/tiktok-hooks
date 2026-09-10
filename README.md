# TikTok Hooks for Claude

A local Claude skill that saves the first 2–3 spoken sentences and actual opening frame from TikTok videos into Markdown or Obsidian.

- Save an individual TikTok link
- Sync unseen videos from a private TikTok collection
- Import only a small initial batch instead of the entire backlog
- Transcribe locally with Whisper
- Read TikTok access from your existing browser session—never from copied passwords or cookie values
- Delete downloaded video and audio after processing
- Optionally schedule daily collection syncs on macOS

Try the zero-install public-link demo at [hookline-blue.vercel.app](https://hookline-blue.vercel.app).

## Requirements

- macOS
- Python 3.10 or newer
- Chrome, Safari, Firefox, Brave, or Edge logged into TikTok for private collections
- [`ffmpeg`](https://ffmpeg.org/)

Install ffmpeg with Homebrew if needed:

```bash
brew install ffmpeg
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/louisedesadeleer/tiktok-hooks/v1.0.0/install.sh | bash
```

Alternatively, [download v1.0.0](https://github.com/louisedesadeleer/tiktok-hooks/archive/refs/tags/v1.0.0.zip), extract it, and run:

```bash
bash install.sh
```

The installer copies the skill to `~/.claude/skills/tiktok-hooks`, creates an isolated Python environment under `~/.local/share/tiktok-hooks/venv`, and installs `yt-dlp` and local Whisper.

Then ask Claude:

> Set up my TikTok hooks skill.

Claude asks where to save your Markdown file and, optionally, which private collection and logged-in browser to use.

## Examples

> Save this TikTok hook: https://www.tiktok.com/@creator/video/123

> Sync my TikTok hook collection.

> Save my hooks to `~/Documents/MyVault/TikTok Hooks.md`.

> Schedule my TikTok hook collection to sync every morning at 9.

## What stays on your computer

```text
~/.config/tiktok-hooks/config.json
~/.local/share/tiktok-hooks/
  seen.json
  sync.lock
  logs/
  venv/
<markdown directory>/
  TikTok Hooks.md
  assets/tiktok-hooks/<video-id>.jpg
```

TikTok cookies are read locally by `yt-dlp` and are never copied into the configuration or Markdown output. Videos and temporary audio are deleted after every extraction.

## Development

```bash
python3 -m unittest discover -s tests
uvx ruff check .
bash -n install.sh
```
