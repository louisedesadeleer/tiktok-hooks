"""Platform identity and supported URL validation."""

import re
from urllib.parse import urlparse

TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}


def platform_for_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Use an HTTPS TikTok video or Instagram Reel/video-post URL.")
    if parsed.hostname in TIKTOK_HOSTS:
        return "tiktok"
    if parsed.hostname in INSTAGRAM_HOSTS and re.fullmatch(
        r"/(?:reel|reels|p|tv)/[A-Za-z0-9_-]+/?", parsed.path
    ):
        return "instagram"
    raise ValueError(
        "Use a TikTok video or Instagram Reel/video-post link; profiles and Instagram collections are not supported."
    )


def video_key(video: dict) -> str:
    # Preserve existing TikTok IDs, while isolating Instagram IDs and filenames.
    return ("instagram-" if video.get("platform") == "instagram" else "") + str(
        video["id"]
    )


def platform_label(video: dict) -> str:
    return "Instagram" if video.get("platform") == "instagram" else "TikTok"
