---
name: tiktok-hooks
description: Save the opening hook and first frame from a TikTok link, or sync new videos from a private TikTok collection, into a local Markdown or Obsidian swipe file. Use when someone asks to save a TikTok hook, sync their hook collection, configure their hook destination, or schedule collection syncing.
argument-hint: "[TikTok URL]"
---

# TikTok Hooks

Save TikTok openings locally. The bundled Python scripts read TikTok login cookies directly from the user's browser, transcribe on the user's machine, and never retain downloaded videos.

Resolve all script paths relative to this `SKILL.md` file. Use the Python interpreter at `~/.local/share/tiktok-hooks/venv/bin/python` when it exists; otherwise explain that the skill must be installed before syncing.

## First-time setup

Check whether `~/.config/tiktok-hooks/config.json` exists.

If it does not, ask the user:

1. Where should the Markdown file be saved? Accept a normal `.md` path or a file inside an Obsidian vault.
2. Do they want to sync a TikTok collection? If yes, ask for its URL and which browser contains their TikTok login. Default to `chrome` only if they confirm it.
3. How many existing collection videos should the first sync import? Recommend five.

Never ask for cookie values, passwords, or TikTok credentials. The local downloader reads the browser's cookie store itself.

Run:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/configure.py \
  --markdown-path "<absolute-or-home-relative-path>" \
  --collection-url "<url-if-provided>" \
  --browser "<browser-if-provided>" \
  --initial-count <count>
```

Omit collection arguments when the user only wants to save individual links. Tell the user where the configuration and Markdown file were created.

If Python dependencies are missing, explain the install command from this skill's `README.md`. Do not install packages or Homebrew dependencies without permission.

## Save one TikTok

For a request containing an individual TikTok URL, run:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/sync.py \
  --url "<tiktok-url>"
```

Report the exact Markdown destination and whether a new hook was saved or the video was already present.

## Sync a collection

Run:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/sync.py
```

The script checks only the configured number of newest collection entries, processes unseen videos one at a time, and retries failures on the next run. The first collection sync imports only the configured initial count; it does not import the full backlog.

Summarize the number of hooks added and the Markdown destination. If browser-cookie access fails, suggest fully quitting the configured browser and retrying once.

## Scheduling

Do not claim Claude itself runs continuously. The optional scheduler is a macOS `launchd` job that invokes the deterministic Python sync without Claude.

Only offer scheduling after a manual collection sync succeeds. Install it only after explicit approval:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/schedule.py \
  --hour 9 --minute 0
```

To remove it:

```bash
~/.local/share/tiktok-hooks/venv/bin/python <skill-dir>/scripts/schedule.py --remove
```

Explain that the Mac must eventually wake and have network access; missed runs are handled when macOS next has an opportunity to run the job.

## Output contract

Each saved entry contains:

- the exact first two spoken sentences, or three when the first two are unusually short
- a relative link to the extracted first frame
- creator, source URL, save date, and TikTok video ID

Keep the downloaded MP4 and temporary audio only while processing. Persist screenshots, Markdown, configuration, and deduplication state.
