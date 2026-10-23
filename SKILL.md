---
name: tiktok-hooks
description: Save opening speech and first frames from TikTok or Instagram video links to Obsidian, Notion, or Markdown; configure destinations and sync or schedule a TikTok collection.
argument-hint: "[TikTok or Instagram video URL]"
---

# TikTok & Instagram Hooks

Use the bundled Python scripts for extraction and saving. Resolve script paths relative to this file. Use `~/.local/share/tiktok-hooks/venv/bin/python`; if missing, follow the installation section in [README.md](README.md).

## Setup or change destination

Read `~/.config/tiktok-hooks/config.json` if present (or run `scripts/configure.py --show`). Preserve existing settings unless the user asks to change them. Existing configurations without a destination use Markdown.

Ask for missing choices:

- Destination: Obsidian, Notion, or plain Markdown.
- For Obsidian/Markdown: the `.md` path. Obsidian defaults to one note per hook plus a Bases table/gallery; `--layout single` keeps everything in one file.
- For Notion: the parent page URL. Use a normal page, not a database. Explain that the hook text, metadata, and opening image will be uploaded there. Follow the Notion setup section in [README.md](README.md) for a connection token and page access. Never ask for the token in chat or place it in a command argument. The user can run `configure.py --set-notion-token` in their terminal, which prompts privately and saves an owner-only token file, or use `NOTION_TOKEN` for a manual run.
- Optional TikTok collection URL, browser containing its login, and initial import count (default five). Instagram collection syncing is not supported.
- For individual links that need login, the supported browser containing the relevant login. Offer only Chrome, Chromium, Brave, Edge, Firefox, Safari, Opera, or Vivaldi. Never offer Arc or ask whether the user uses Arc; it is unsupported. If the user mentions Arc, ask them to log into TikTok or Instagram in one of the supported browsers. Apply this same browser list when configuring a TikTok collection. Do not assume a browser; both platforms use the configured browser.

Examples:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --destination obsidian --markdown-path "<vault>/Video Hooks.md"

~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --destination notion --notion-page "<page-url-or-id>"
```

Optional settings: `--collection-url "<TikTok-collection-url>" --browser "<browser>" --initial-count 5`. Never ask for browser cookie values or passwords; `yt-dlp` reads the local cookie store.

Selecting a destination does not copy existing hooks. Resubmit individual URLs or sync the initial collection batch to save there. Local output and each Notion parent page have separate duplicate tracking. Preserve the skill name and installation paths for backward compatibility.

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

Obsidian notes include platform/video ID properties and retain `tiktok_id` for TikTok compatibility. Existing `.base` files are never overwritten. Notion uses one child page per hook with an uploaded image, quote, metadata, and source bookmark. Transcription runs locally for both destinations. Temporary video/audio are deleted after processing; opening images and local state remain.
