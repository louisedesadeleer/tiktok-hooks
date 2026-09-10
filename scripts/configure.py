#!/usr/bin/env python3
"""Configure the TikTok Hooks skill without handling browser credentials."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

CONFIG_DIR = Path.home() / ".config" / "tiktok-hooks"
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
    markdown_value = arguments.markdown_path or current.get("markdown_path")
    if not markdown_value:
        sys.exit("A --markdown-path is required for first-time setup.")

    markdown = Path(markdown_value).expanduser().resolve()
    if markdown.suffix.lower() != ".md":
        sys.exit("The Markdown destination must end in .md.")

    collection_url = arguments.collection_url or current.get("collection_url")
    browser = arguments.browser or current.get("browser")
    if collection_url and not browser:
        sys.exit("A --browser is required when configuring a private collection.")

    if arguments.assets_path:
        assets = Path(arguments.assets_path).expanduser().resolve()
    elif arguments.markdown_path or not current.get("assets_path"):
        assets = markdown.parent / "assets" / "tiktok-hooks"
    else:
        assets = Path(current["assets_path"]).expanduser().resolve()

    initial_count = arguments.initial_count or current.get("initial_import_count", 5)
    check_count = arguments.check_count or current.get("check_count", 30)
    if check_count < initial_count:
        sys.exit("--check-count must be at least --initial-count.")

    layout = getattr(arguments, "layout", None) or current.get("layout", "single")

    config = {
        "layout": layout,
        "markdown_path": str(markdown),
        "assets_path": str(assets),
        "collection_url": collection_url,
        "browser": browser,
        "whisper_model": arguments.model or current.get("whisper_model", "base"),
        "initial_import_count": initial_count,
        "check_count": check_count,
    }

    markdown.parent.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    if layout == "notes":
        markdown.with_suffix("").mkdir(parents=True, exist_ok=True)
    elif not markdown.exists():
        markdown.write_text("# TikTok Hooks\n\n")

    write_json(CONFIG_PATH, config)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure the TikTok Hooks skill.")
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
    if config["layout"] == "notes":
        folder = Path(config["markdown_path"]).with_suffix("")
        print(f"Notes folder: {folder}")
        print(f"Bases table: {folder.with_suffix('.base')} (created on first sync)")
    else:
        print(f"Markdown: {config['markdown_path']}")
    if config.get("collection_url"):
        print(f"Collection: {config['collection_url']}")


if __name__ == "__main__":
    main()
