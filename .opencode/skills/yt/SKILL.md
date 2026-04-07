---
name: yt
description: "YouTube CLI tool for searching videos, fetching transcripts, browsing playlists, and searching watch history. Use this skill whenever the user wants to search YouTube, get video captions/subtitles/transcripts, look up their YouTube history, list or search playlists, or do anything YouTube-related from the terminal. Triggers on: youtube, video search, transcript, captions, subtitles, playlist, watch history, yt."
---

# YouTube CLI Tool

A Python CLI for YouTube operations — search, transcripts, playlists, and history.

## Quick Reference

| Command | API Key Needed | Description |
|---------|---------------|-------------|
| `search <query>` | No (scrapes YouTube) | Search YouTube videos |
| `transcript <video>` | No | Fetch video transcript/captions |
| `playlists` | **Yes** | List channel playlists |
| `playlist-items <id>` | **Yes** | List videos in a playlist |
| `history <query>` | **Yes** | Search your liked/uploaded videos |

## Running the Tool

The base command (run from any directory):

```bash
YT="uv run --project /home/zzwf/.claude/skills/yt/scripts python3 -m yt_cli.main"
```

### Search (no API key needed)

```bash
$YT search "python tutorial"
$YT search "rust programming" -n 5
$YT --json search "machine learning"
```

### Transcripts (no API key needed)

```bash
$YT transcript VIDEO_ID --text          # plain text
$YT transcript "https://www.youtube.com/watch?v=VIDEO_ID"  # timestamped segments
$YT transcript VIDEO_ID -l es           # Spanish
$YT --json transcript VIDEO_ID          # JSON with timestamps
```

### Playlists (requires API key)

```bash
$YT --api-key "$YOUTUBE_API_KEY" playlists -c CHANNEL_ID
$YT --api-key "$YOUTUBE_API_KEY" playlist-items PLxxxxxx
$YT --api-key "$YOUTUBE_API_KEY" --json playlist-items PLxxxxxx
```

### History (requires API key)

```bash
$YT --api-key "$YOUTUBE_API_KEY" history "search term"
```

## JSON Output

Add `--json` before the command for machine-readable output:

```bash
$YT --json search "topic"
```

## Environment Variable

Set `YOUTUBE_API_KEY` to avoid passing `--api-key` each time:

```bash
export YOUTUBE_API_KEY="your-key-here"
```

## How It Works

- **Search**: Scrapes YouTube search results directly (no key needed). Falls back to Invidious public API, then YouTube Data API v3 if a key is available.
- **Transcripts**: Uses `youtube-transcript-api` to fetch captions. Supports language selection with `-l`. Use `--text` for plain text.
- **Playlists / History**: Requires a YouTube Data API v3 key. History searches liked and uploaded videos (YouTube API doesn't expose raw watch history — for that, suggest Google Takeout).

## Common Agent Patterns

**Search and get transcript:**
```bash
# 1. Search for a video
uv run --project /home/zzwf/.claude/skills/yt/scripts python3 -m yt_cli.main --json search "topic" 
# 2. Grab transcript of the best match
uv run --project /home/zzwf/.claude/skills/yt/scripts python3 -m yt_cli.main transcript VIDEO_ID --text
```

## Limitations

- Watch history search is limited to liked/uploaded videos (YouTube API restriction)
- Transcript availability depends on the video having captions enabled
