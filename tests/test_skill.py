import argparse
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import configure
import hooks
import schedule
import sync


class HookTests(unittest.TestCase):
    def test_extracts_two_sentences(self):
        transcript = (
            "This is a useful first sentence with a promise. "
            "This second sentence explains what comes next. Ignore this sentence."
        )

        self.assertEqual(
            hooks.extract_hook(transcript),
            "This is a useful first sentence with a promise. "
            "This second sentence explains what comes next.",
        )

    def test_adds_third_sentence_after_short_opening(self):
        self.assertEqual(
            hooks.extract_hook("Wait. Listen. This third sentence completes the hook."),
            "Wait. Listen. This third sentence completes the hook.",
        )

    def test_markdown_uses_relative_frame_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "vault" / "TikTok Hooks.md"
            frame = root / "vault" / "assets" / "tiktok-hooks" / "123.jpg"
            video = {
                "id": "123",
                "title": "Example",
                "uploader": "creator",
                "url": "https://www.tiktok.com/@creator/video/123",
                "hook": "Start with a specific promise.",
                "frame_path": str(frame),
                "saved_at": "2026-08-28T10:00:00+00:00",
            }

            result = hooks.markdown_entry(video, markdown)

            self.assertIn("assets/tiktok-hooks/123.jpg", result)
            self.assertIn("Start with a specific promise.", result)
            self.assertNotIn(str(root), result)


class ConfigurationTests(unittest.TestCase):
    def test_first_setup_creates_markdown_assets_and_private_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config" / "config.json"
            markdown = root / "vault" / "TikTok Hooks.md"
            arguments = argparse.Namespace(
                markdown_path=str(markdown),
                assets_path=None,
                collection_url="https://www.tiktok.com/@creator/collection/hooks-123",
                browser="chrome",
                model="base",
                initial_count=5,
                check_count=30,
            )

            with patch.object(configure, "CONFIG_PATH", config_path):
                config = configure.configure(arguments)

            self.assertEqual(config["markdown_path"], str(markdown))
            self.assertEqual(markdown.read_text(), "# TikTok Hooks\n\n")
            self.assertTrue(Path(config["assets_path"]).is_dir())
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)


class SyncTests(unittest.TestCase):
    def test_failed_forced_reprocess_preserves_existing_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            frame = assets / "123.jpg"
            frame.write_bytes(b"saved frame")
            media = root / "video.mp4"
            media.touch()

            def extract(_ffmpeg, _media, output, audio):
                output.write_bytes(b"replacement frame")
                audio.touch()

            model = types.SimpleNamespace(
                transcribe=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("transcription failed")
                )
            )
            video = {
                "id": "123",
                "title": "Example",
                "uploader": "creator",
                "url": "https://www.tiktok.com/@creator/video/123",
            }

            with (
                patch.object(sync, "download_video", return_value=media),
                patch.object(sync, "extract_media", side_effect=extract),
                self.assertRaisesRegex(RuntimeError, "transcription failed"),
            ):
                sync.process_video(
                    video,
                    {"assets_path": str(assets)},
                    model,
                    "ffmpeg",
                    root / "work",
                )

            self.assertEqual(frame.read_bytes(), b"saved frame")

    def test_first_collection_sync_selects_only_configured_count(self):
        videos = [{"id": str(index)} for index in range(10)]
        state = {"saved": [], "collection_initialized": False}

        selected = sync.select_collection_videos(
            videos,
            state,
            {"initial_import_count": 3},
        )

        self.assertEqual([video["id"] for video in selected], ["0", "1", "2"])
        self.assertEqual(state["saved"], [])
        self.assertEqual(state["skipped"], [str(index) for index in range(3, 10)])
        self.assertTrue(state["collection_initialized"])

    def test_later_collection_sync_selects_only_unseen_videos(self):
        videos = [{"id": "new"}, {"id": "seen"}]
        state = {"saved": ["seen"], "collection_initialized": True}

        selected = sync.select_collection_videos(videos, state, {})

        self.assertEqual(selected, [{"id": "new"}])

    def test_legacy_state_separates_saved_and_skipped_ids_from_markdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "seen.json"
            markdown = root / "Hooks.md"
            state_path.write_text(
                json.dumps(
                    {
                        "seen": ["saved", "skipped"],
                        "collection_initialized": True,
                    }
                )
            )
            markdown.write_text("- TikTok ID: `saved`\n")

            with patch.object(sync, "STATE_PATH", state_path):
                state = sync.load_state(markdown)

            self.assertEqual(state["saved"], ["saved"])
            self.assertEqual(state["skipped"], ["skipped"])
            self.assertNotIn("seen", state)

    def test_collection_sync_saves_only_initial_batch_and_deduplicates_backlog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            state_path = root / "seen.json"
            markdown = root / "Hooks.md"
            assets = root / "assets"
            config_path.write_text(
                json.dumps(
                    {
                        "markdown_path": str(markdown),
                        "assets_path": str(assets),
                        "collection_url": "https://www.tiktok.com/@creator/collection/hooks-123",
                        "initial_import_count": 2,
                    }
                )
            )
            videos = [
                {
                    "id": str(index),
                    "title": f"Video {index}",
                    "uploader": "creator",
                    "url": f"https://www.tiktok.com/@creator/video/{index}",
                }
                for index in range(3)
            ]

            def process(video, _config, _model, _ffmpeg, _workdir):
                frame = assets / f"{video['id']}.jpg"
                frame.parent.mkdir(exist_ok=True)
                frame.touch()
                return {
                    **video,
                    "hook": f"Hook {video['id']}.",
                    "frame_path": str(frame),
                    "saved_at": "2026-08-28T10:00:00+00:00",
                }

            arguments = argparse.Namespace(url=None, force=False)
            whisper = types.SimpleNamespace(load_model=lambda _name: object())
            with (
                patch.object(sync, "CONFIG_PATH", config_path),
                patch.object(sync, "STATE_PATH", state_path),
                patch.object(sync, "list_collection", return_value=videos),
                patch.object(sync, "check_downloader"),
                patch.object(sync, "check_dependencies", return_value="ffmpeg"),
                patch.object(sync, "process_video", side_effect=process),
                patch.dict(sys.modules, {"whisper": whisper}),
            ):
                completed, failed = sync.sync(arguments)

            self.assertEqual([video["id"] for video in completed], ["0", "1"])
            self.assertEqual(failed, [])
            self.assertNotIn("Video 2", markdown.read_text())
            state = json.loads(state_path.read_text())
            self.assertEqual(state["saved"], ["0", "1"])
            self.assertEqual(state["skipped"], ["2"])

    def test_explicit_url_can_save_a_skipped_backlog_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            state_path = root / "seen.json"
            markdown = root / "Hooks.md"
            assets = root / "assets"
            config_path.write_text(
                json.dumps(
                    {
                        "markdown_path": str(markdown),
                        "assets_path": str(assets),
                    }
                )
            )
            state_path.write_text(
                json.dumps({"seen": ["6"], "collection_initialized": True})
            )
            video = {
                "id": "6",
                "title": "Skipped video",
                "uploader": "creator",
                "url": "https://www.tiktok.com/@creator/video/6",
            }

            def process(candidate, _config, _model, _ffmpeg, _workdir):
                frame = assets / "6.jpg"
                frame.parent.mkdir(exist_ok=True)
                frame.touch()
                return {
                    **candidate,
                    "hook": "Explicitly requested hook.",
                    "frame_path": str(frame),
                    "saved_at": "2026-08-28T10:00:00+00:00",
                }

            arguments = argparse.Namespace(
                url="https://www.tiktok.com/@creator/video/6", force=False
            )
            whisper = types.SimpleNamespace(load_model=lambda _name: object())
            with (
                patch.object(sync, "CONFIG_PATH", config_path),
                patch.object(sync, "STATE_PATH", state_path),
                patch.object(sync, "inspect_url", return_value=video),
                patch.object(sync, "check_downloader"),
                patch.object(sync, "check_dependencies", return_value="ffmpeg"),
                patch.object(sync, "process_video", side_effect=process),
                patch.dict(sys.modules, {"whisper": whisper}),
            ):
                completed, failed = sync.sync(arguments)

            self.assertEqual([item["id"] for item in completed], ["6"])
            self.assertEqual(failed, [])
            self.assertIn("Skipped video", markdown.read_text())

    def test_markdown_entries_are_prepended_after_heading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "Hooks.md"
            markdown.write_text("# TikTok Hooks\n\nOlder entry\n")
            frame = root / "assets" / "123.jpg"
            frame.parent.mkdir()
            frame.touch()
            video = {
                "id": "123",
                "title": "New entry",
                "uploader": "creator",
                "url": "https://www.tiktok.com/@creator/video/123",
                "hook": "A new hook.",
                "frame_path": str(frame),
                "saved_at": "2026-08-28T10:00:00+00:00",
            }

            sync.append_markdown(markdown, [video])

            result = markdown.read_text()
            self.assertLess(result.index("New entry"), result.index("Older entry"))


class ScheduleTests(unittest.TestCase):
    def test_plist_runs_sync_with_installed_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            python = data / "venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.touch()

            with patch.object(schedule, "DATA_DIR", data):
                result = schedule.plist(9, 30)

            self.assertEqual(result["StartCalendarInterval"], {"Hour": 9, "Minute": 30})
            self.assertEqual(result["ProgramArguments"][0], str(python))
            self.assertEqual(result["ProgramArguments"][1], str(schedule.SYNC_SCRIPT))


if __name__ == "__main__":
    unittest.main()


class NotesLayoutTests(unittest.TestCase):
    def _video(self, root):
        return {
            "id": "123",
            "title": 'Why "marketing" pulls you down: a #story',
            "uploader": "creator",
            "url": "https://www.tiktok.com/@creator/video/123",
            "hook": "Start with a specific promise.",
            "frame_path": str(root / "vault" / "assets" / "tiktok-hooks" / "123.jpg"),
            "saved_at": "2026-08-28T10:00:00+00:00",
        }

    def test_note_filename_is_safe_and_unique(self):
        name = hooks.note_filename(self._video(Path("/x")))
        self.assertEqual(
            name, "@creator — Why marketing pulls you down a story (123).md"
        )

    def test_note_has_properties_and_relative_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            note = root / "vault" / "TikTok Hooks" / "note.md"
            text = hooks.note_entry(self._video(root), note)
            self.assertTrue(text.startswith("---\n"))
            self.assertIn('hook: "Start with a specific promise."', text)
            self.assertIn('frame: "[[123.jpg]]"', text)
            self.assertIn("saved: 2026-08-28", text)
            self.assertIn("(<../assets/tiktok-hooks/123.jpg>)", text)

    def test_write_notes_creates_folder_and_base_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault" / ".obsidian").mkdir(parents=True)
            markdown = root / "vault" / "Tiktok" / "TikTok Hooks.md"
            folder = sync.write_notes(markdown, [self._video(root)])
            self.assertEqual(folder, root / "vault" / "Tiktok" / "TikTok Hooks")
            self.assertEqual(len(list(folder.glob("*.md"))), 1)
            base = markdown.with_suffix(".base")
            self.assertIn('file.inFolder("Tiktok/TikTok Hooks")', base.read_text())
            base.write_text("custom")
            sync.write_notes(markdown, [self._video(root)])
            self.assertEqual(base.read_text(), "custom")
