"""Save hook pages and opening images using the official Notion API."""

import json
import os
import re
import uuid
from datetime import datetime
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
            host in {"notion.so", "www.notion.so", "app.notion.com", "notion.site"}
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


# Database columns the skill fills when a column with that name and type exists.
DATABASE_COLUMNS = {
    "Hook": "rich_text",
    "Creator": "rich_text",
    "Platform": "select",
    "Source": "url",
    "Saved": "date",
    "Video ID": "rich_text",
}


class NotionDestination:
    def __init__(self, config: dict):
        database = config.get("notion_database_id")
        self.database_id = page_id(database) if database else None
        # parent_id doubles as the duplicate-tracking key for this destination.
        self.parent_id = self.database_id or page_id(config["notion_page_id"])
        self._data_source_id = None
        self._columns = None
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
                404: "Share the parent page or database with the Notion connection and check its ID.",
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

    def create_database(self, title: str = "Video Hooks") -> str:
        # Full-page database inside the parent page, with every column the skill fills.
        result = self.request(
            "POST",
            "/databases",
            {
                "parent": {"type": "page_id", "page_id": self.parent_id},
                "title": rich_text(title),
                "is_inline": False,
                "initial_data_source": {
                    "properties": {
                        "Name": {"title": {}},
                        "Hook": {"rich_text": {}},
                        "Creator": {"rich_text": {}},
                        "Platform": {
                            "select": {
                                "options": [
                                    {"name": "TikTok", "color": "pink"},
                                    {"name": "Instagram", "color": "purple"},
                                ]
                            }
                        },
                        "Saved": {"date": {}},
                        "Source": {"url": {}},
                        "Video ID": {"rich_text": {}},
                    }
                },
            },
        )
        return str(uuid.UUID(result["id"]))

    def database_schema(self) -> tuple[str, dict[str, str]]:
        # Resolve the database's data source and its column names → types once.
        if self._data_source_id is None:
            database = self.request("GET", f"/databases/{self.database_id}")
            sources = database.get("data_sources") or []
            if not sources:
                raise NotionError(
                    "The Notion database has no data source; check the database link."
                )
            data_source_id = sources[0]["id"]
            schema = self.request("GET", f"/data_sources/{data_source_id}")
            self._columns = {
                name: column.get("type")
                for name, column in (schema.get("properties") or {}).items()
            }
            if "title" not in self._columns.values():
                raise NotionError("The Notion database has no title column.")
            self._data_source_id = data_source_id
        return self._data_source_id, self._columns

    def has_column(self, name: str) -> bool:
        return self._columns.get(name) == DATABASE_COLUMNS[name]

    def find_existing_row(self, key: str, marker: str) -> str | None:
        data_source_id, columns = self.database_schema()
        if self.has_column("Video ID"):
            condition = {"property": "Video ID", "rich_text": {"equals": key}}
        else:
            title = next(name for name, kind in columns.items() if kind == "title")
            condition = {"property": title, "title": {"ends_with": marker}}
        result = self.request(
            "POST",
            f"/data_sources/{data_source_id}/query",
            {"filter": condition, "page_size": 1},
        )
        rows = result.get("results") or []
        return rows[0]["id"] if rows else None

    def row_properties(self, video: dict, key: str, marker: str) -> dict:
        _, columns = self.database_schema()
        title_column = next(name for name, kind in columns.items() if kind == "title")
        title = f"@{video['uploader']} — {video['title']}"[:180]
        if not self.has_column("Video ID"):
            title += " " + marker
        values = {
            "Hook": {"rich_text": rich_text(video["hook"])},
            "Creator": {"rich_text": rich_text("@" + str(video["uploader"]).lstrip("@"))},
            "Platform": {"select": {"name": platform_label(video)}},
            "Source": {"url": video["url"]},
            "Saved": {
                "date": {
                    "start": datetime.fromisoformat(video["saved_at"])
                    .replace(microsecond=0)
                    .isoformat()
                }
            },
            "Video ID": {"rich_text": rich_text(key)},
        }
        properties = {title_column: {"title": rich_text(title)}}
        properties.update(
            {name: value for name, value in values.items() if self.has_column(name)}
        )
        return properties

    def save(self, video: dict) -> str:
        key = video_key(video)
        marker = f"[hook:{key}]"
        if self.database_id:
            existing = self.find_existing_row(key, marker)
            parent = {"type": "data_source_id", "data_source_id": self._data_source_id}
            properties = self.row_properties(video, key, marker)
        else:
            existing = self.find_existing(marker)
            parent = {"type": "page_id", "page_id": self.parent_id}
            title = f"@{video['uploader']} — {video['title']}"[:180] + " " + marker
            properties = {"title": {"type": "title", "title": rich_text(title)}}
        if existing:
            return existing
        upload_id = self.upload_frame(Path(video["frame_path"]))
        result = self.request(
            "POST",
            "/pages",
            {
                "parent": parent,
                "properties": properties,
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
