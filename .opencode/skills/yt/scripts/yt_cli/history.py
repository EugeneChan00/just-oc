"""YouTube watch history and playlist operations — requires YouTube Data API v3 + OAuth or API key."""

from __future__ import annotations

from typing import Any

import requests

YT_DATA_API = "https://www.googleapis.com/youtube/v3"


def _require_key(api_key: str | None) -> str:
    if not api_key:
        raise RuntimeError(
            "This feature requires a YouTube API key. "
            "Set YOUTUBE_API_KEY env var or pass --api-key."
        )
    return api_key


def list_playlists(api_key: str | None = None, channel_id: str = "mine", max_results: int = 25) -> list[dict[str, Any]]:
    """List playlists for a channel.  ``channel_id='mine'`` requires an OAuth token; a plain API key needs an explicit channel ID."""
    key = _require_key(api_key)
    params: dict[str, Any] = {
        "part": "snippet,contentDetails",
        "maxResults": min(max_results, 50),
        "key": key,
    }
    if channel_id == "mine":
        params["mine"] = "true"
    else:
        params["channelId"] = channel_id
    r = requests.get(f"{YT_DATA_API}/playlists", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return [
        {
            "playlist_id": item["id"],
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "item_count": item["contentDetails"].get("itemCount", 0),
            "url": f"https://www.youtube.com/playlist?list={item['id']}",
        }
        for item in data.get("items", [])
    ]


def list_playlist_items(
    playlist_id: str,
    api_key: str | None = None,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """List videos inside a playlist."""
    key = _require_key(api_key)
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(items) < max_results:
        params: dict[str, Any] = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": min(50, max_results - len(items)),
            "key": key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{YT_DATA_API}/playlistItems", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        for it in data.get("items", []):
            s = it["snippet"]
            vid = s.get("resourceId", {}).get("videoId", "")
            items.append({
                "video_id": vid,
                "title": s.get("title", ""),
                "channel": s.get("videoOwnerChannelTitle", ""),
                "position": s.get("position", 0),
                "published": s.get("publishedAt", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def search_history(
    query: str,
    api_key: str | None = None,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Search the user's liked / watch-later / uploaded videos via the Data API.

    Note: The YouTube Data API v3 does not expose raw watch history.
    This searches the user's *liked videos* playlist (``LL``) and *uploads*
    as the closest available proxy.  For full history, consider Google Takeout.
    """
    key = _require_key(api_key)
    # Search across user's activities
    params: dict[str, Any] = {
        "part": "snippet",
        "forMine": "true",
        "type": "video",
        "q": query,
        "maxResults": min(max_results, 50),
        "key": key,
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
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return results
