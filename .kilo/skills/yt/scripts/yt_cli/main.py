"""yt-cli — YouTube search, transcripts, history & playlists from the terminal."""

from __future__ import annotations

import json
import os
import sys

import click

from yt_cli.search import search_videos
from yt_cli.transcript import get_transcript
from yt_cli.history import list_playlists, list_playlist_items, search_history


def _get_api_key(ctx_key: str | None) -> str | None:
    return ctx_key or os.environ.get("YOUTUBE_API_KEY")


def _output(data, as_json: bool):
    if as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if isinstance(data, list):
            for i, item in enumerate(data, 1):
                click.echo(f"\n--- {i} ---")
                for k, v in item.items():
                    click.echo(f"  {k}: {v}")
        elif isinstance(data, str):
            click.echo(data)
        else:
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))


@click.group()
@click.option("--api-key", envvar="YOUTUBE_API_KEY", default=None, help="YouTube Data API v3 key (or set YOUTUBE_API_KEY env var)")
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, api_key, use_json):
    """yt-cli — search YouTube, grab transcripts, browse playlists & history."""
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["json"] = use_json


# ---------- search ----------


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("-n", "--max-results", default=10, show_default=True, help="Number of results")
@click.pass_context
def search(ctx, query, max_results):
    """Search YouTube videos.  Works without an API key (uses Invidious); falls back to Data API if key is set."""
    q = " ".join(query)
    try:
        results = search_videos(q, api_key=_get_api_key(ctx.obj["api_key"]), max_results=max_results)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    _output(results, ctx.obj["json"])


# ---------- transcript ----------


@cli.command()
@click.argument("video")
@click.option("-l", "--lang", default="en", show_default=True, help="Language code")
@click.option("--text", "as_text", is_flag=True, help="Plain text (no timestamps)")
@click.pass_context
def transcript(ctx, video, lang, as_text):
    """Fetch the transcript / captions for a video.  Pass a URL or video ID."""
    try:
        data = get_transcript(video, lang=lang, as_text=as_text)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    _output(data, ctx.obj["json"])


# ---------- playlists ----------


@cli.command()
@click.option("-c", "--channel-id", default=None, help="Channel ID (omit to list your own — requires OAuth token)")
@click.option("-n", "--max-results", default=25, show_default=True)
@click.pass_context
def playlists(ctx, channel_id, max_results):
    """List playlists for a channel.  Requires --api-key."""
    try:
        cid = channel_id or "mine"
        results = list_playlists(api_key=_get_api_key(ctx.obj["api_key"]), channel_id=cid, max_results=max_results)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    _output(results, ctx.obj["json"])


@cli.command("playlist-items")
@click.argument("playlist_id")
@click.option("-n", "--max-results", default=50, show_default=True)
@click.pass_context
def playlist_items(ctx, playlist_id, max_results):
    """List videos in a playlist.  Requires --api-key."""
    try:
        results = list_playlist_items(playlist_id, api_key=_get_api_key(ctx.obj["api_key"]), max_results=max_results)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    _output(results, ctx.obj["json"])


# ---------- history ----------


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("-n", "--max-results", default=25, show_default=True)
@click.pass_context
def history(ctx, query, max_results):
    """Search your YouTube history / uploads.  Requires --api-key.

    Note: YouTube Data API doesn't expose raw watch history.
    This searches your liked & uploaded videos as a proxy.
    For full history, use Google Takeout.
    """
    q = " ".join(query)
    try:
        results = search_history(q, api_key=_get_api_key(ctx.obj["api_key"]), max_results=max_results)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    _output(results, ctx.obj["json"])


if __name__ == "__main__":
    cli()
