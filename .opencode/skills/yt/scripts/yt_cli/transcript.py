"""Fetch YouTube video transcripts using youtube-transcript-api."""

from __future__ import annotations

import urllib.parse
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str:
    """Extract a YouTube video ID from any common URL form or bare ID.

    Supported formats:
      - https://www.youtube.com/watch?v=ID
      - https://youtube.com/watch?v=ID&t=120
      - https://m.youtube.com/watch?v=ID
      - https://music.youtube.com/watch?v=ID
      - https://youtu.be/ID
      - https://youtu.be/ID?t=30
      - https://www.youtube.com/embed/ID
      - https://www.youtube.com/v/ID
      - https://www.youtube.com/shorts/ID
      - https://www.youtube.com/live/ID
      - Bare 11-char video ID  (e.g. aImUujll89w)
    """
    url_or_id = url_or_id.strip()

    # Short-link: youtu.be/ID
    if "youtu.be/" in url_or_id:
        path = url_or_id.split("youtu.be/")[-1]
        return path.split("?")[0].split("&")[0].split("/")[0]

    # Any youtube.com variant (www, m, music, gaming, etc.)
    if "youtube.com" in url_or_id:
        parsed = urllib.parse.urlparse(url_or_id)

        # /watch?v=ID  (most common)
        qs = urllib.parse.parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]

        # Path-based: /embed/ID, /v/ID, /shorts/ID, /live/ID
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("embed", "v", "shorts", "live"):
            return parts[1].split("?")[0]

    # Bare video ID (typically 11 chars, alphanumeric + _ -)
    return url_or_id


def get_transcript(
    video: str,
    lang: str = "en",
    as_text: bool = False,
) -> list[dict[str, Any]] | str:
    """Fetch transcript for a video.

    Args:
        video: YouTube video URL or ID.
        lang: Preferred language code (default ``en``).
        as_text: If True return plain text instead of timestamped segments.

    Returns:
        List of ``{text, start, duration}`` dicts, or a single string if *as_text*.
    """
    vid = extract_video_id(video)
    ytt = YouTubeTranscriptApi()
    try:
        transcript = ytt.fetch(vid, languages=[lang, "en"])
    except Exception:
        # Try to find any available transcript
        transcript_list = ytt.list(vid)
        # Pick first available
        for t in transcript_list:
            transcript = ytt.fetch(vid, languages=[t.language_code])
            break
        else:
            raise RuntimeError(f"No transcripts available for video {vid}")

    snippets = []
    for seg in transcript.snippets:
        snippets.append({
            "text": seg.text,
            "start": seg.start,
            "duration": seg.duration,
        })

    if as_text:
        return "\n".join(s["text"] for s in snippets)
    return snippets
