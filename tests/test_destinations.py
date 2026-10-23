import argparse
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import configure
import hooks
import notion
import sources
import sync

PARENT = "12345678-1234-1234-1234-123456789abc"
UPLOAD = "22345678-1234-1234-1234-123456789abc"


def arguments(**overrides):
    values = {
        "markdown_path": None,
        "assets_path": None,
        "collection_url": None,
        "browser": None,
        "model": None,
        "initial_count": None,
        "check_count": None,
        "destination": None,
        "notion_page": None,
        "notion_token_file": None,
        "set_notion_token": False,
        "layout": None,
    }
    return argparse.Namespace(**(values | overrides))


def video(root, platform="instagram", identity="123"):
    frame = root / "opening.jpg"
    frame.write_bytes(b"jpeg test bytes")
    return {
        "id": identity,
        "platform": platform,
        "title": "A hook",
        "uploader": "creator",
        "url": "https://www.instagram.com/reel/ABC/"
        if platform == "instagram"
        else "https://www.tiktok.com/@creator/video/123",
        "hook": "First sentence. Second sentence.",
        "frame_path": str(frame),
        "saved_at": "2026-10-23T10:00:00+00:00",
    }


class SourceTests(unittest.TestCase):
    def test_supported_and_rejected_urls(self):
        for path in ("reel/ABC/", "reels/ABC", "p/ABC/", "tv/ABC/"):
            self.assertEqual(
                sources.platform_for_url("https://www.instagram.com/" + path),
                "instagram",
            )
        self.assertEqual(
            sources.platform_for_url("https://vm.tiktok.com/ABC/"), "tiktok"
        )
        for url in (
            "https://instagram.com/creator/",
            "https://instagram.com/stories/name/123/",
            "http://instagram.com/reel/ABC/",
            "https://instagram.com.evil.test/reel/ABC/",
            "https://user@instagram.com/reel/ABC/",
            "https://example.com/video/1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sources.platform_for_url(url)

    def test_inspect_instagram_preserves_source_and_identity(self):
        url = "https://www.instagram.com/reel/ABC/"
        response = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "123", "title": "Reel", "uploader": "creator"}),
        )
        with patch.object(sync, "run", return_value=response):
            item = sync.inspect_url(url, {})
        self.assertEqual(item["url"], url)
        self.assertEqual(item["platform"], "instagram")
        self.assertEqual(sources.video_key(item), "instagram-123")

    def test_instagram_uses_username_instead_of_display_name(self):
        item = sync.video_from_entry(
            {"id": "123", "uploader": "Creator Full Name", "channel": "creator_handle"},
            platform="instagram",
            source_url="https://instagram.com/reel/ABC/",
        )
        self.assertEqual(item["uploader"], "creator_handle")

    def test_carousel_rejected_with_actionable_error(self):
        response = types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"_type": "playlist", "entries": [{"id": "123"}]}),
        )
        with (
            patch.object(sync, "run", return_value=response),
            self.assertRaisesRegex(sync.SyncError, "single video"),
        ):
            sync.inspect_url("https://instagram.com/p/ABC/", {})

    def test_instagram_output_has_platform_and_unique_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = video(root)
            note = hooks.note_entry(item, root / "note.md")
            self.assertIn('platform: "instagram"', note)
            self.assertIn('instagram_id: "123"', note)
            self.assertNotIn("tiktok_id:", note)
            self.assertIn("Watch on Instagram", note)
            self.assertIn(
                "Instagram ID:", hooks.markdown_entry(item, root / "Hooks.md")
            )
            self.assertNotEqual(
                hooks.note_filename(item),
                hooks.note_filename(item | {"platform": "tiktok"}),
            )


class DestinationConfigTests(unittest.TestCase):
    def test_notion_without_markdown_and_switch_back_to_obsidian(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(configure, "CONFIG_PATH", root / "config.json"),
                patch.dict(os.environ, {"TIKTOK_HOOKS_DATA_HOME": str(root / "data")}),
            ):
                config = configure.configure(
                    arguments(destination="notion", notion_page=PARENT)
                )
                self.assertIsNone(config["markdown_path"])
                self.assertEqual(config["notion_page_id"], PARENT)
                self.assertFalse(list(root.glob("*.md")))
                config = configure.configure(
                    arguments(
                        destination="obsidian",
                        markdown_path=str(root / "vault" / "Hooks.md"),
                    )
                )
                self.assertEqual(config["layout"], "notes")
                self.assertEqual(
                    Path(config["assets_path"]),
                    (root / "vault" / "assets" / "tiktok-hooks").resolve(),
                )
                self.assertTrue((root / "vault" / "Hooks").is_dir())

    def test_notion_requires_valid_parent(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(configure, "CONFIG_PATH", Path(directory) / "config.json"),
        ):
            with self.assertRaisesRegex(SystemExit, "notion-page"):
                configure.configure(arguments(destination="notion"))
            with self.assertRaisesRegex(SystemExit, "Notion page"):
                configure.configure(
                    arguments(destination="notion", notion_page="invalid")
                )

    def test_token_saved_privately_and_not_in_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_file = root / "token"
            with (
                patch.object(configure, "CONFIG_PATH", root / "config.json"),
                patch.object(
                    configure.getpass, "getpass", return_value="secret-test-value"
                ),
            ):
                config = configure.configure(
                    arguments(
                        destination="notion",
                        notion_page=PARENT,
                        assets_path=str(root / "assets"),
                        notion_token_file=str(token_file),
                        set_notion_token=True,
                    )
                )
            self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(token_file.read_text().strip(), "secret-test-value")
            self.assertNotIn("secret-test-value", json.dumps(config))

    def test_notion_page_url_normalizes_id(self):
        self.assertEqual(
            notion.page_id(
                "https://www.notion.so/Hooks-" + PARENT.replace("-", "") + "?v=ignored"
            ),
            PARENT,
        )
        with self.assertRaises(ValueError):
            notion.page_id("https://evil.test/" + PARENT)


class NotionTests(unittest.TestCase):
    def destination(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "test-secret"}):
            return notion.NotionDestination({"notion_page_id": PARENT})

    def test_upload_then_create_page_with_image_and_quote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = video(root)
            destination = self.destination()
            with patch.object(
                destination,
                "request",
                side_effect=[
                    {"results": [], "has_more": False},
                    {"id": UPLOAD},
                    {"status": "uploaded"},
                    {"id": "new-page"},
                ],
            ) as request:
                self.assertEqual(destination.save(item), "new-page")
            calls = request.call_args_list
            self.assertEqual(calls[1].args[:2], ("POST", "/file_uploads"))
            self.assertIn(b"jpeg test bytes", calls[2].kwargs["body"])
            self.assertIn("multipart/form-data", calls[2].kwargs["content_type"])
            page = calls[3].args[2]
            self.assertEqual(page["parent"]["page_id"], PARENT)
            self.assertEqual(page["children"][0]["image"]["file_upload"]["id"], UPLOAD)
            self.assertEqual(
                page["children"][1]["quote"]["rich_text"][0]["text"]["content"],
                item["hook"],
            )
            self.assertEqual(page["children"][3]["bookmark"]["url"], item["url"])

    def test_retry_finds_page_on_later_page_without_uploading_again(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = self.destination()
            with patch.object(
                destination,
                "request",
                side_effect=[
                    {"results": [], "has_more": True, "next_cursor": "cursor"},
                    {
                        "results": [
                            {
                                "id": "existing",
                                "type": "child_page",
                                "child_page": {"title": "A hook [hook:instagram-123]"},
                            }
                        ],
                        "has_more": False,
                    },
                ],
            ) as request:
                self.assertEqual(destination.save(video(Path(directory))), "existing")
            self.assertEqual(request.call_count, 2)
            self.assertIn("start_cursor=cursor", request.call_args.args[1])

    def test_failed_upload_does_not_create_page(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = self.destination()
            with (
                patch.object(
                    destination,
                    "request",
                    side_effect=[
                        {"results": []},
                        {"id": UPLOAD},
                        {"status": "failed"},
                    ],
                ) as request,
                self.assertRaisesRegex(notion.NotionError, "uploading"),
            ):
                destination.save(video(Path(directory)))
            self.assertEqual(request.call_count, 3)

    def test_api_request_and_sanitized_failure(self):
        destination = self.destination()
        response = io.BytesIO(b'{"id":"response"}')
        with patch.object(notion, "urlopen", return_value=response) as transport:
            self.assertEqual(
                destination.request("POST", "/pages", {"example": "value"}),
                {"id": "response"},
            )
            request = transport.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.notion.com/v1/pages")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
            self.assertEqual(json.loads(request.data), {"example": "value"})
        for error in (
            HTTPError("url", 401, "test-secret", {}, None),
            URLError("test-secret"),
        ):
            with (
                patch.object(notion, "urlopen", side_effect=error),
                self.assertRaises(notion.NotionError) as caught,
            ):
                destination.request("GET", "/pages/123")
            self.assertNotIn("test-secret", str(caught.exception))

    def test_private_token_file_used_without_environment(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {}, clear=True),
        ):
            token_file = Path(directory) / "token"
            token_file.write_text("file-token")
            token_file.chmod(0o600)
            config = {"notion_page_id": PARENT, "notion_token_file": str(token_file)}
            self.assertEqual(notion.NotionDestination(config).token, "file-token")
            token_file.chmod(0o644)
            with self.assertRaisesRegex(notion.NotionError, "chmod 600"):
                notion.NotionDestination(config)

    def test_long_transcript_split_into_api_sized_text(self):
        parts = notion.rich_text("x" * 4500)
        self.assertEqual(
            [len(part["text"]["content"]) for part in parts], [2000, 2000, 500]
        )


class SyncDestinationTests(unittest.TestCase):
    def test_notion_failure_retries_without_marking_saved_and_keeps_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = video(root)
            state_path = root / "seen.json"
            state_path.write_text(
                json.dumps(
                    {"saved": ["123"], "skipped": [], "collection_initialized": True}
                )
            )
            config = {
                "destination": "notion",
                "notion_page_id": PARENT,
                "assets_path": str(root),
            }
            args = argparse.Namespace(url=item["url"], force=False)
            sink = types.SimpleNamespace(
                parent_id=PARENT, save=lambda _item: "new-page"
            )
            whisper = types.SimpleNamespace(load_model=lambda _name: object())
            with (
                patch.object(sync, "load_config", return_value=config),
                patch.object(sync, "STATE_PATH", state_path),
                patch.object(sync, "NotionDestination", return_value=sink),
                patch.object(sync, "inspect_url", return_value=item),
                patch.object(sync, "check_downloader"),
                patch.object(sync, "check_dependencies", return_value="ffmpeg"),
                patch.object(sync, "process_video", return_value=item),
                patch.dict(sys.modules, {"whisper": whisper}),
            ):
                with patch.object(
                    sink, "save", side_effect=notion.NotionError("offline")
                ):
                    completed, failed = sync.sync(args)
                self.assertFalse(completed)
                self.assertEqual(len(failed), 1)
                self.assertEqual(
                    json.loads(state_path.read_text())["notion"][PARENT]["saved"], []
                )
                completed, failed = sync.sync(args)
                self.assertEqual(len(completed), 1)
                self.assertFalse(failed)
                state = json.loads(state_path.read_text())
                self.assertEqual(state["saved"], ["123"])
                self.assertEqual(state["notion"][PARENT]["saved"], ["instagram-123"])
                with patch.object(sync, "process_video") as process:
                    completed, failed = sync.sync(args)
                    process.assert_not_called()

    def test_same_tiktok_can_be_saved_to_notion_after_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = video(root, platform="tiktok")
            state_path = root / "seen.json"
            state_path.write_text(json.dumps({"saved": ["123"], "skipped": []}))
            sink = types.SimpleNamespace(
                parent_id=PARENT, save=lambda _item: "new-page"
            )
            with (
                patch.object(
                    sync,
                    "load_config",
                    return_value={"destination": "notion", "notion_page_id": PARENT},
                ),
                patch.object(sync, "STATE_PATH", state_path),
                patch.object(sync, "NotionDestination", return_value=sink),
                patch.object(sync, "inspect_url", return_value=item),
                patch.object(sync, "check_downloader"),
                patch.object(sync, "check_dependencies", return_value="ffmpeg"),
                patch.object(sync, "process_video", return_value=item),
                patch.dict(
                    sys.modules,
                    {
                        "whisper": types.SimpleNamespace(
                            load_model=lambda _name: object()
                        )
                    },
                ),
            ):
                completed, failed = sync.sync(
                    argparse.Namespace(url=item["url"], force=False)
                )
            self.assertEqual(len(completed), 1)
            self.assertFalse(failed)
            self.assertEqual(
                json.loads(state_path.read_text())["notion"][PARENT]["saved"], ["123"]
            )


DATABASE = "32345678-1234-1234-1234-123456789abc"
DATA_SOURCE = "42345678-1234-1234-1234-123456789abc"
FULL_SCHEMA = {
    "Name": {"type": "title"},
    "Hook": {"type": "rich_text"},
    "Creator": {"type": "rich_text"},
    "Platform": {"type": "select"},
    "Source": {"type": "url"},
    "Saved": {"type": "date"},
    "Video ID": {"type": "rich_text"},
}


class NotionDatabaseTests(unittest.TestCase):
    def destination(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "test-secret"}):
            return notion.NotionDestination(
                {"notion_page_id": PARENT, "notion_database_id": DATABASE}
            )

    def test_database_takes_precedence_and_is_tracking_key(self):
        self.assertEqual(self.destination().parent_id, DATABASE)

    def test_creates_row_with_columns_and_image(self):
        with tempfile.TemporaryDirectory() as directory:
            item = video(Path(directory))
            destination = self.destination()
            with patch.object(
                destination,
                "request",
                side_effect=[
                    {"data_sources": [{"id": DATA_SOURCE}]},
                    {"properties": FULL_SCHEMA},
                    {"results": []},
                    {"id": UPLOAD},
                    {"status": "uploaded"},
                    {"id": "new-row"},
                ],
            ) as request:
                self.assertEqual(destination.save(item), "new-row")
            calls = request.call_args_list
            self.assertEqual(calls[0].args[:2], ("GET", f"/databases/{DATABASE}"))
            query = calls[2].args[2]["filter"]
            self.assertEqual(query["property"], "Video ID")
            self.assertEqual(query["rich_text"]["equals"], "instagram-123")
            page = calls[5].args[2]
            self.assertEqual(page["parent"]["data_source_id"], DATA_SOURCE)
            props = page["properties"]
            title = props["Name"]["title"][0]["text"]["content"]
            self.assertEqual(title, "@creator — A hook")
            self.assertEqual(props["Platform"]["select"]["name"], "Instagram")
            self.assertEqual(props["Source"]["url"], item["url"])
            self.assertEqual(props["Saved"]["date"]["start"], item["saved_at"])
            self.assertEqual(props["Creator"]["rich_text"][0]["text"]["content"], "@creator")
            self.assertEqual(page["children"][0]["image"]["file_upload"]["id"], UPLOAD)

    def test_existing_row_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = self.destination()
            with patch.object(
                destination,
                "request",
                side_effect=[
                    {"data_sources": [{"id": DATA_SOURCE}]},
                    {"properties": FULL_SCHEMA},
                    {"results": [{"id": "existing-row"}]},
                ],
            ) as request:
                self.assertEqual(destination.save(video(Path(directory))), "existing-row")
            self.assertEqual(request.call_count, 3)

    def test_minimal_database_keeps_marker_in_title_and_skips_missing_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = self.destination()
            with patch.object(
                destination,
                "request",
                side_effect=[
                    {"data_sources": [{"id": DATA_SOURCE}]},
                    {"properties": {"Title": {"type": "title"}, "Hook": {"type": "url"}}},
                    {"results": []},
                    {"id": UPLOAD},
                    {"status": "uploaded"},
                    {"id": "row"},
                ],
            ) as request:
                destination.save(video(Path(directory)))
            calls = request.call_args_list
            self.assertEqual(calls[2].args[2]["filter"]["title"]["ends_with"], "[hook:instagram-123]")
            props = calls[5].args[2]["properties"]
            self.assertEqual(list(props), ["Title"])
            self.assertTrue(
                props["Title"]["title"][0]["text"]["content"].endswith("[hook:instagram-123]")
            )

    def test_configure_database_and_switch_back_to_page(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(configure, "CONFIG_PATH", Path(directory) / "config.json"):
                config = configure.configure(
                    arguments(
                        destination="notion",
                        notion_database="https://app.notion.com/p/" + DATABASE.replace("-", ""),
                    )
                )
                self.assertEqual(config["notion_database_id"], DATABASE)
                config = configure.configure(arguments(notion_page=PARENT))
                self.assertIsNone(config["notion_database_id"])
                self.assertEqual(config["notion_page_id"], PARENT)

    def test_create_database_payload(self):
        with patch.dict(os.environ, {"NOTION_TOKEN": "test-secret"}):
            destination = notion.NotionDestination({"notion_page_id": PARENT})
        with patch.object(destination, "request", return_value={"id": DATABASE}) as request:
            self.assertEqual(destination.create_database(), DATABASE)
        method, path, payload = request.call_args.args
        self.assertEqual((method, path), ("POST", "/databases"))
        self.assertEqual(payload["parent"]["page_id"], PARENT)
        columns = payload["initial_data_source"]["properties"]
        for name, kind in notion.DATABASE_COLUMNS.items():
            self.assertIn(kind, columns[name])
        self.assertIn("title", columns["Name"])

    def test_configure_creates_database_in_parent_page(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(configure, "CONFIG_PATH", Path(directory) / "config.json"),
            patch.dict(os.environ, {"NOTION_TOKEN": "test-secret"}),
            patch.object(
                notion.NotionDestination, "create_database", return_value=DATABASE
            ) as create,
        ):
            config = configure.configure(
                arguments(
                    destination="notion",
                    notion_page=PARENT,
                    notion_create_database=True,
                )
            )
        create.assert_called_once()
        self.assertEqual(config["notion_database_id"], DATABASE)
        self.assertEqual(config["notion_page_id"], PARENT)
