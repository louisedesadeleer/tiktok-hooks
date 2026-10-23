"""Save hook pages and opening images using the official Notion API."""

import json
import os
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from sources import platform_label, video_key

API_URL = "https://api.notion.com/v1"
API_VERSION = "2025-09-03"
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "tiktok-hooks" / "notion-token"


class NotionError(RuntimeError):
    pass


def page_id(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("https://"):
        parsed = urlparse(candidate)
        host = parsed.hostname or ""
        if not (
            host in {"notion.so", "www.notion.so", "notion.site"}
            or host.endswith(".notion.site")
        ):
            raise ValueError("Use a Notion page URL or page ID.")
        candidate = parsed.path.rstrip("/").split("/")[-1]
    match = re.search(
        r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$",
        candidate,
    )
    if not match:
        raise ValueError("Use a Notion page URL or its 32-character page ID.")
    return str(uuid.UUID(match.group(1)))


def rich_text(text: str) -> list[dict]:
    # Notion caps each text object at 2,000 characters and arrays at 100 items.
    text = str(text)[:200000]
    return [
        {"type": "text", "text": {"content": text[i : i + 2000]}}
        for i in range(0, len(text), 2000)
    ]


def text_block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text(text)}}


class NotionDestination:
    def __init__(self, config: dict):
        self.parent_id = page_id(config["notion_page_id"])
        self.token = os.environ.get("NOTION_TOKEN", "").strip()
        if not self.token:
            token_file = Path(
                config.get("notion_token_file") or DEFAULT_TOKEN_FILE
            ).expanduser()
            try:
                if token_file.stat().st_mode & 0o077:
                    raise NotionError(
                        f"Restrict the Notion token file to its owner: chmod 600 {token_file}"
                    )
                self.token = token_file.read_text().strip()
            except OSError:
                raise NotionError(
                    "Set NOTION_TOKEN or run configure.py --set-notion-token in your terminal."
                ) from None
        if not self.token:
            raise NotionError("The Notion token is empty.")

    def request(
        self,
        method: str,
        path: str,
        payload=None,
        *,
        body=None,
        content_type="application/json",
    ) -> dict:
        if payload is not None:
            body = json.dumps(payload).encode()
        request = Request(
            API_URL + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": API_VERSION,
                "Content-Type": content_type,
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            # Never print response bodies, request headers, or the token.
            hint = {
                401: "Check the Notion connection token.",
                403: "Give the Notion connection read, insert, and update content access.",
                404: "Share the parent page with the Notion connection and check its page ID.",
                429: "Notion is rate limiting requests; retry the sync later.",
            }.get(
                error.code,
                "Retry the sync; if it persists, check the Notion connection and page.",
            )
            code = error.code
            error.close()
            raise NotionError(f"Notion returned HTTP {code}. {hint}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise NotionError(
                "Notion could not be reached or returned an invalid response. Retry the sync."
            ) from None

    def find_existing(self, marker: str) -> str | None:
        # Recover after a lost create-page response, without duplicating the hook.
        cursor = ""
        while True:
            query = f"?page_size=100{cursor}"
            result = self.request("GET", f"/blocks/{self.parent_id}/children{query}")
            for block in result.get("results", []):
                if block.get("type") == "child_page" and block["child_page"][
                    "title"
                ].endswith(marker):
                    return block["id"]
            if not result.get("has_more"):
                return None
            cursor = "&start_cursor=" + quote(result["next_cursor"], safe="")

    def upload_frame(self, frame: Path) -> str:
        if frame.stat().st_size > 5 * 1024 * 1024:
            raise NotionError(
                "The opening image exceeds 5 MB; reduce its size before saving to Notion."
            )
        upload = self.request(
            "POST",
            "/file_uploads",
            {
                "mode": "single_part",
                "filename": "opening.jpg",
                "content_type": "image/jpeg",
            },
        )
        upload_id = str(uuid.UUID(upload["id"]))
        boundary = "hookline-" + uuid.uuid4().hex
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="opening.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n"
            ).encode()
            + frame.read_bytes()
            + f"\r\n--{boundary}--\r\n".encode()
        )
        result = self.request(
            "POST",
            f"/file_uploads/{upload_id}/send",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        if result.get("status") != "uploaded":
            raise NotionError(
                "Notion did not finish uploading the opening image. Retry the sync."
            )
        return upload_id

    def save(self, video: dict) -> str:
        marker = f"[hook:{video_key(video)}]"
        existing = self.find_existing(marker)
        if existing:
            return existing
        upload_id = self.upload_frame(Path(video["frame_path"]))
        title = f"@{video['uploader']} — {video['title']}"[:180] + " " + marker
        result = self.request(
            "POST",
            "/pages",
            {
                "parent": {"type": "page_id", "page_id": self.parent_id},
                "properties": {"title": {"type": "title", "title": rich_text(title)}},
                "children": [
                    {
                        "object": "block",
                        "type": "image",
                        "image": {
                            "type": "file_upload",
                            "file_upload": {"id": upload_id},
                        },
                    },
                    text_block("quote", video["hook"]),
                    text_block(
                        "paragraph",
                        f"Creator: @{video['uploader']}\nPlatform: {platform_label(video)}\nSaved: {video['saved_at']}\nVideo ID: {video['id']}",
                    ),
                    {
                        "object": "block",
                        "type": "bookmark",
                        "bookmark": {"url": video["url"]},
                    },
                ],
            },
        )
        return result["id"]
