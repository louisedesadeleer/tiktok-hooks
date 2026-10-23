#!/usr/bin/env python3
"""Configure the TikTok Hooks skill without handling browser credentials."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from notion import DEFAULT_TOKEN_FILE, page_id

CONFIG_DIR = Path(
    os.environ.get("TIKTOK_HOOKS_CONFIG_HOME", Path.home() / ".config" / "tiktok-hooks")
)
CONFIG_PATH = CONFIG_DIR / "config.json"
TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    try:
        value = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as error:
        sys.exit(f"Invalid configuration at {CONFIG_PATH}: {error}")

    return value if isinstance(value, dict) else {}


def validate_collection_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in TIKTOK_HOSTS:
        raise argparse.ArgumentTypeError("must be an HTTPS tiktok.com URL")
    if "/collection/" not in parsed.path:
        raise argparse.ArgumentTypeError("must be a TikTok collection URL")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def configure(arguments: argparse.Namespace) -> dict:
    current = read_config()
    destination = getattr(arguments, "destination", None) or current.get(
        "destination", "markdown"
    )
    markdown_value = arguments.markdown_path or current.get("markdown_path")
    if destination != "notion" and not markdown_value:
        sys.exit("A --markdown-path is required for first-time setup.")

    markdown = Path(markdown_value).expanduser().resolve() if markdown_value else None
    if markdown and markdown.suffix.lower() != ".md":
        sys.exit("The Markdown destination must end in .md.")

    collection_url = arguments.collection_url or current.get("collection_url")
    browser = arguments.browser or current.get("browser")
    if collection_url and not browser:
        sys.exit("A --browser is required when configuring a private collection.")

    notion_page = getattr(arguments, "notion_page", None) or current.get(
        "notion_page_id"
    )
    if destination == "notion":
        if not notion_page:
            sys.exit("A --notion-page URL or page ID is required for Notion.")
        try:
            notion_page = page_id(notion_page)
        except ValueError as error:
            sys.exit(str(error))

    if arguments.assets_path:
        assets = Path(arguments.assets_path).expanduser().resolve()
    elif destination == "notion":
        assets = (
            Path(
                os.environ.get(
                    "TIKTOK_HOOKS_DATA_HOME",
                    Path.home() / ".local" / "share" / "tiktok-hooks",
                )
            )
            / "assets"
        )
    elif (
        arguments.markdown_path
        or not current.get("assets_path")
        or current.get("destination") == "notion"
    ):
        assets = markdown.parent / "assets" / "tiktok-hooks"
    else:
        assets = Path(current["assets_path"]).expanduser().resolve()

    initial_count = arguments.initial_count or current.get("initial_import_count", 5)
    check_count = arguments.check_count or current.get("check_count", 30)
    if check_count < initial_count:
        sys.exit("--check-count must be at least --initial-count.")

    layout = getattr(arguments, "layout", None) or (
        "notes"
        if destination == "obsidian" and current.get("destination") != "obsidian"
        else current.get("layout", "single")
    )

    config = {
        "destination": destination,
        "layout": layout,
        "markdown_path": str(markdown) if markdown else None,
        "assets_path": str(assets),
        "collection_url": collection_url,
        "browser": browser,
        "whisper_model": arguments.model or current.get("whisper_model", "base"),
        "initial_import_count": initial_count,
        "check_count": check_count,
        "notion_page_id": notion_page,
        "notion_token_file": str(
            Path(
                getattr(arguments, "notion_token_file", None)
                or current.get("notion_token_file")
                or DEFAULT_TOKEN_FILE
            )
            .expanduser()
            .resolve()
        ),
    }

    assets.mkdir(parents=True, exist_ok=True)
    if destination != "notion":
        markdown.parent.mkdir(parents=True, exist_ok=True)
        if layout == "notes":
            markdown.with_suffix("").mkdir(parents=True, exist_ok=True)
        elif not markdown.exists():
            markdown.write_text("# TikTok Hooks\n\n")

    if getattr(arguments, "set_notion_token", False):
        token = getpass.getpass("Notion connection token (hidden): ").strip()
        if not token:
            sys.exit("Token was empty; configuration was not changed.")
        token_file = Path(config["notion_token_file"])
        token_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(token + "\n")

    write_json(CONFIG_PATH, config)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure the TikTok Hooks skill.")
    parser.add_argument("--destination", choices=("obsidian", "notion", "markdown"))
    parser.add_argument(
        "--notion-page", help="Parent Notion page URL or ID (not a database)"
    )
    parser.add_argument(
        "--notion-token-file", help="Path to a private token file for unattended syncs"
    )
    parser.add_argument(
        "--set-notion-token",
        action="store_true",
        help="Prompt securely for a Notion token in the terminal",
    )
    parser.add_argument("--markdown-path")
    parser.add_argument("--assets-path")
    parser.add_argument("--collection-url", type=validate_collection_url)
    parser.add_argument("--browser")
    parser.add_argument("--model", choices=("tiny", "base", "small"))
    parser.add_argument(
        "--layout",
        choices=("single", "notes"),
        help="single: one Markdown file; notes: one note per hook plus an Obsidian Bases table",
    )
    parser.add_argument("--initial-count", type=positive_integer)
    parser.add_argument("--check-count", type=positive_integer)
    parser.add_argument("--show", action="store_true")
    arguments = parser.parse_args()

    if arguments.show:
        config = read_config()
        if not config:
            sys.exit(f"No configuration found at {CONFIG_PATH}.")
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return

    config = configure(arguments)
    print(f"Configuration: {CONFIG_PATH}")
    if config["destination"] == "notion":
        print(f"Notion parent page: {config['notion_page_id']}")
    elif config["layout"] == "notes":
        folder = Path(config["markdown_path"]).with_suffix("")
        print(f"Notes folder: {folder}")
        print(f"Bases table: {folder.with_suffix('.base')} (created on first sync)")
    else:
        print(f"Markdown: {config['markdown_path']}")
    if config.get("collection_url"):
        print(f"Collection: {config['collection_url']}")


if __name__ == "__main__":
    main()
