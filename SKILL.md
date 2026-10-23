---
name: tiktok-hooks
description: Save opening speech and first frames from TikTok or Instagram video links to Obsidian, Notion, or Markdown; configure destinations and sync or schedule a TikTok collection.
argument-hint: "[TikTok or Instagram video URL]"
---

# TikTok & Instagram Hooks

Use the bundled Python scripts for extraction and saving. Resolve script paths relative to this file. Use `~/.local/share/tiktok-hooks/venv/bin/python`; if missing, follow the installation section in [README.md](README.md).

## Check requirements first

Before setup, and whenever a sync fails because something is missing, run the check with the system Python (it works before installation):

```bash
python3 <skill-dir>/scripts/doctor.py
```

It reports macOS, Python 3.10+, Homebrew, ffmpeg, the skill files, Whisper and yt-dlp in the skill's environment, the Whisper model cache, and the configuration. For each item marked ✗, tell the user what is missing and give them the exact fix command it prints (for example `brew install ffmpeg`, the Homebrew installer, or `bash install.sh`). Homebrew is only required when ffmpeg is missing. Ask before running any installer yourself, and never run the Homebrew installer for the user; it needs their password in their own terminal. Continue setup only once every required item passes.

## Setup or change destination

Read `~/.config/tiktok-hooks/config.json` if present (or run `scripts/configure.py --show`). Preserve existing settings unless the user asks to change them. Existing configurations without a destination use Markdown.

Ask for missing choices:

- Destination: Obsidian, Notion, or plain Markdown.
- Save hooks as a database by default, so every hook is a row with sortable columns and a gallery of opening frames.
- For Obsidian: the `.md` path inside the vault. The default layout is one note per hook plus a Bases database (table and gallery views). Use `--layout single` only if the user asks for one file.
- For plain Markdown: the `.md` path; hooks go into that single file.
- For Notion: a database. If a Notion connector is available in this conversation, create a full-page database named "Video Hooks" where the user wants it (top level unless they name a parent) with columns `Name` (title), `Hook` (text), `Creator` (text), `Platform` (select: TikTok, Instagram), `Saved` (date), `Source` (URL), `Video ID` (text), add a gallery view sorted by Saved descending, and pass its URL with `--notion-database`. Otherwise ask for a parent page and use `--notion-page "<page>" --notion-create-database`, which creates the same database inside that page after the token is saved. Either way, the user must add their Notion connection to the database (or its parent page) through ••• → Connections. Use `--notion-page` alone (child pages, no database) only if the user asks for it. Explain that the hook text, metadata, and opening image will be uploaded there. Follow the Notion setup section in [README.md](README.md) for a connection token and page access. Never ask for the token in chat or place it in a command argument. The user can run `configure.py --set-notion-token` in their terminal, which prompts privately and saves an owner-only token file, or use `NOTION_TOKEN` for a manual run.
- Optional TikTok collection URL, browser containing its login, and initial import count (default five). Instagram collection syncing is not supported.
- For individual links that need login, the supported browser containing the relevant login. Offer only Chrome, Chromium, Brave, Edge, Firefox, Safari, Opera, or Vivaldi. Never offer Arc or ask whether the user uses Arc; it is unsupported. If the user mentions Arc, ask them to log into TikTok or Instagram in one of the supported browsers. Apply this same browser list when configuring a TikTok collection. Do not assume a browser; both platforms use the configured browser.

Examples:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --destination obsidian --markdown-path "<vault>/Video Hooks.md"

~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --destination notion --notion-database "<database-url>" --set-notion-token

~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --destination notion --notion-page "<parent-page-url>" --notion-create-database --set-notion-token
```

Commands with `--set-notion-token` prompt for a hidden token, so the user must run them in their own terminal.

Optional settings: `--collection-url "<TikTok-collection-url>" --browser "<browser>" --initial-count 5`. Never ask for browser cookie values or passwords; `yt-dlp` reads the local cookie store.

Selecting a destination does not copy existing hooks. Resubmit individual URLs or sync the initial collection batch to save there. Local output, each Notion parent page, and each Notion database have separate duplicate tracking. Preserve the skill name and installation paths for backward compatibility.

## Save one video

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/sync.py --url "<video-url>"
```

Accept TikTok video links and Instagram `/reel/`, `/reels/`, single-video `/p/`, or `/tv/` links. Instagram profiles, saved collections, photo posts, and multi-item carousels are unsupported. Report an access failure honestly; login may be needed even for public Instagram videos. Do not try to bypass platform restrictions.

Report the saved destination and count, or that the video was already saved. `--force` is for local output only; existing Notion pages can be edited in Notion. Preserve `[hook:…]` title markers for retry deduplication.

## Sync a TikTok collection

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/sync.py
```

The script checks a bounded window of newest entries, processes unseen videos sequentially, and saves each success immediately. First sync imports only the configured initial count. Failed videos remain eligible for retry while in the checked window. An explicit URL can import a skipped backlog video.

For browser-cookie errors, suggest fully quitting the configured browser and retrying once. For Notion errors, report the actionable message (token, page sharing, rate limit, or network). Do not repeatedly retry a failed service in a loop. Summarize added hooks and failures separately.

## Scheduling

Offer scheduling after a manual collection sync succeeds. Install it when the user requests or approves scheduling:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/schedule.py --hour 9 --minute 0
```

Use `--remove` to remove the schedule. This is a macOS `launchd` job running Python, not a continuously running Claude agent. The Mac must have network access and an opportunity to run. Notion schedules need the token file because a shell's `NOTION_TOKEN` is not automatically passed to `launchd`.

## Output and privacy

Save the first two spoken sentences (three when the first two are under 12 words), opening JPEG, creator, platform, source URL, save date, and video ID. Speech recognition can be imperfect; this does not extract on-screen text or rank hooks.

Obsidian notes include platform/video ID properties and retain `tiktok_id` for TikTok compatibility. Existing `.base` files are never overwritten. In a Notion database each hook is a row with those columns, and its page body holds the uploaded image, quote, metadata, and source bookmark. With `--notion-page` alone, each hook is a child page with the same body. Transcription runs locally for both destinations. Temporary video/audio are deleted after processing; opening images and local state remain.

## Uninstall

When the user asks to uninstall or reset the skill, have them run this in their own terminal (it asks for confirmation; `--yes` skips it, `--keep-whisper-model` keeps the downloaded model):

```bash
bash ~/.claude/skills/tiktok-hooks/uninstall.sh
```

It removes the daily job, the skill files, the Python environment (Whisper and yt-dlp), configuration, the Notion token, sync state, and the Whisper model cache. It keeps saved hooks, ffmpeg, and Homebrew. Saved Notion databases or pages and the Notion connection are removed in Notion itself; offer to delete the database through a Notion connector only when the user asks.
