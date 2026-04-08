"""YouTube video search — works without API key by scraping YouTube directly, with Invidious and Data API v3 fallbacks."""

from __future__ import annotations

import json
from typing import Any

import requests

INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
]

YT_DATA_API = "https://www.googleapis.com/youtube/v3"

_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Accept-Language": "en-US,en;q=0.9",
}


def _try_scrape_youtube(query: str, max_results: int = 10) -> list[dict[str, Any]] | None:
    """Scrape YouTube search results directly (no key required).

    YouTube embeds initial search data as JSON inside the HTML page.
    """
    import urllib.parse

    url = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query})
    try:
        r = requests.get(url, headers=_YT_HEADERS, timeout=15)
        r.raise_for_status()
        # Find the start of ytInitialData and use json.JSONDecoder to parse the object
        marker = "var ytInitialData = "
        idx = r.text.find(marker)
        if idx == -1:
            return None
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(r.text, idx + len(marker))

        # Navigate the nested structure to find video renderers
        contents = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        results: list[dict[str, Any]] = []
        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                vr = item.get("videoRenderer")
                if not vr:
                    continue
                vid = vr.get("videoId", "")
                title_runs = vr.get("title", {}).get("runs", [])
                title = title_runs[0]["text"] if title_runs else ""
                author = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                length_text = vr.get("lengthText", {}).get("simpleText", "")
                view_text = vr.get("viewCountText", {}).get("simpleText", "")
                published = vr.get("publishedTimeText", {}).get("simpleText", "")

                results.append({
                    "video_id": vid,
                    "title": title,
                    "author": author,
                    "length": length_text,
                    "views": view_text,
                    "published": published,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        return results if results else None
    except Exception:
        return None


def _try_invidious(query: str, max_results: int = 10) -> list[dict[str, Any]] | None:
    """Search via public Invidious instances (no key required)."""
    params = {"q": query, "type": "video"}
    for base in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(f"{base}/api/v1/search", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            results = []
            for item in data[:max_results]:
                if item.get("type") != "video":
                    continue
                results.append({
                    "video_id": item.get("videoId", ""),
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "length_seconds": item.get("lengthSeconds", 0),
                    "view_count": item.get("viewCount", 0),
                    "published": item.get("publishedText", ""),
                    "url": f"https://www.youtube.com/watch?v={item.get('videoId', '')}",
                })
            return results
        except Exception:
            continue
    return None


def _search_yt_data_api(query: str, api_key: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search via YouTube Data API v3."""
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results, 50),
        "key": api_key,
    }
    r = requests.get(f"{YT_DATA_API}/search", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        vid = item.get("id", {}).get("videoId", "")
        results.append({
            "video_id": vid,
            "title": snippet.get("title", ""),
            "author": snippet.get("channelTitle", ""),
            "published": snippet.get("publishedAt", ""),
            "description": snippet.get("description", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return results


def search_videos(query: str, api_key: str | None = None, max_results: int = 10) -> list[dict[str, Any]]:
    """Search YouTube videos.

    Priority: YouTube scrape -> Invidious -> Data API (if key) -> error.
    """
    if not api_key:
        # Try direct YouTube scrape first
        results = _try_scrape_youtube(query, max_results)
        if results:
            return results
        # Try Invidious
        results = _try_invidious(query, max_results)
        if results is not None:
            return results
    if api_key:
        return _search_yt_data_api(query, api_key, max_results)
    raise RuntimeError("All free search methods failed and no API key provided. Set YOUTUBE_API_KEY or pass --api-key.")
