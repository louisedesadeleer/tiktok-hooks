"""Pure helpers for extracting and formatting video hooks."""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from sources import platform_label, video_key

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
MAX_SENTENCES = 3
MIN_WORDS = 12
MAX_NOTE_TITLE = 60
UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|#^\[\]]')

BASE_TEMPLATE = """\
# Obsidian Bases view for TikTok Hooks. Safe to edit; the sync only creates
# this file when it is missing.
filters:
  and:
    - file.inFolder("{folder}")
    - file.ext == "md"
formulas:
  opening_frame: image(frame)
properties:
  formula.opening_frame:
    displayName: Opening frame
  note.hook:
    displayName: Hook
  note.creator:
    displayName: Creator
  note.saved:
    displayName: Saved
  note.source:
    displayName: Source
  note.platform:
    displayName: Platform
  note.video_id:
    displayName: Video ID
views:
  - type: table
    name: Hooks
    order:
      - formula.opening_frame
      - file.name
      - note.hook
      - note.creator
      - note.saved
      - note.source
    sort:
      - property: note.saved
        direction: DESC
      - property: file.name
        direction: ASC
  - type: cards
    name: Gallery
    image: note.frame
    imageAspectRatio: 0.5625
    order:
      - file.name
      - note.hook
      - note.creator
    sort:
      - property: note.saved
        direction: DESC
"""


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


def saved_date(video: dict) -> str:
    return datetime.fromisoformat(video["saved_at"]).astimezone().date().isoformat()


def markdown_entry(video: dict, markdown_path: Path) -> str:
    frame = Path(video["frame_path"])
    relative_frame = Path(os.path.relpath(frame, markdown_path.parent)).as_posix()
    title = clean_inline(video.get("title", ""), "Untitled video")
    creator = clean_inline(video.get("uploader", ""), "unknown")
    hook = clean_inline(video.get("hook", ""), "No speech detected.")
    saved = saved_date(video)

    return (
        f"## {title}\n\n"
        f"![Opening frame](<{relative_frame}>)\n\n"
        f"> {hook}\n\n"
        f"- Creator: @{creator.lstrip('@')}\n"
        f"- Source: <{video['url']}>\n"
        f"- Saved: {saved}\n"
        f"- {platform_label(video)} ID: `{video['id']}`\n\n"
    )


def note_filename(video: dict) -> str:
    """One note per hook: '<creator> — <short title>.md', unique via the video ID."""
    creator = UNSAFE_FILENAME.sub(
        "", clean_inline(video.get("uploader", ""), "unknown").lstrip("@")
    )
    title = clean_inline(video.get("title", ""), "")
    if not title or title == "Untitled video":
        title = clean_inline(video.get("hook", ""), "")
    title = UNSAFE_FILENAME.sub("", title).strip(" .")
    if len(title) > MAX_NOTE_TITLE:
        title = title[:MAX_NOTE_TITLE].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    stem = f"@{creator} — {title}" if title else f"@{creator}"
    return f"{stem} ({video_key(video)}).md"


def note_entry(video: dict, note_path: Path) -> str:
    """A note with YAML properties so Obsidian Bases can show it as a table row."""
    frame = Path(video["frame_path"])
    relative_frame = Path(os.path.relpath(frame, note_path.parent)).as_posix()
    title = clean_inline(video.get("title", ""), "Untitled video")
    creator = "@" + clean_inline(video.get("uploader", ""), "unknown").lstrip("@")
    hook = clean_inline(video.get("hook", ""), "No speech detected.")
    saved = saved_date(video)
    frame_link = f"[[{frame.name}]]"

    def yaml(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return (
        "---\n"
        f"{video.get('platform', 'tiktok')}_id: {yaml(video['id'])}\n"
        f"platform: {yaml(video.get('platform', 'tiktok'))}\n"
        f"video_id: {yaml(video['id'])}\n"
        f"creator: {yaml(creator)}\n"
        f"title: {yaml(title)}\n"
        f"hook: {yaml(hook)}\n"
        f"source: {yaml(video['url'])}\n"
        f"saved: {saved}\n"
        f"frame: {yaml(frame_link)}\n"
        "tags:\n"
        f"  - {video.get('platform', 'tiktok')}-hook\n"
        "---\n\n"
        f"![Opening frame](<{relative_frame}>)\n\n"
        f"> {hook}\n\n"
        f"Creator: {creator} · [Watch on {platform_label(video)}]({video['url']}) · Saved {saved}\n"
    )


def base_file(folder_name: str) -> str:
    return BASE_TEMPLATE.format(folder=folder_name)
