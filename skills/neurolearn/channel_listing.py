"""List public channel uploads with data from YouTube."""
from __future__ import annotations

import heapq
import json
from collections.abc import Iterator
from datetime import date, datetime

import click
from rich.table import Table
from rich.text import Text

from skills.neurolearn import youtube_api
from skills.neurolearn.utils.console import make_console

_PUBLICATION_TYPES: tuple[youtube_api.PublicationType, ...] = ("videos", "shorts", "streams")


def _typed_uploads(
    channel_id: str, kind: youtube_api.PublicationType,
) -> Iterator[tuple[youtube_api.PlaylistVideo, str]]:
    for upload in youtube_api.iter_channel_uploads(channel_id, kind):
        yield upload, kind


def _list_publications(
    channel_id: str, kinds: tuple[youtube_api.PublicationType, ...], limit: int,
    since: date | None, until: date | None,
) -> list[dict]:
    # Each playlist is newest-first. A lazy merge only advances the playlist
    # whose next upload is needed to fill the global window.
    uploads = heapq.merge(
        *(_typed_uploads(channel_id, kind) for kind in kinds),
        key=lambda entry: entry[0].published_at, reverse=True,
    )
    selected = []
    for upload, kind in uploads:
        day = upload.published_at.date()
        if since and day < since:
            break
        if until and day > until:
            continue
        selected.append((upload, kind))
        if len(selected) == limit:
            break

    details = youtube_api.fetch_video_details(upload.video_id for upload, _ in selected)
    rows = []
    for upload, kind in selected:
        detail = details.get(upload.video_id)
        path = "shorts/" if kind == "shorts" else "watch?v="
        rows.append({
            "video_id": upload.video_id,
            "url": f"https://www.youtube.com/{path}{upload.video_id}",
            "title": upload.title,
            "published_at": upload.published_at.isoformat(),
            "publication_type": kind,
            "duration_sec": detail.duration_sec if detail else None,
            "view_count": detail.view_count if detail else None,
            "like_count": detail.like_count if detail else None,
            "comment_count": detail.comment_count if detail else None,
        })
    return rows


@click.command(name="channel-list")
@click.argument("source")
@click.option("--limit", type=click.IntRange(min=1), default=50, show_default=True,
              help="Maximum number of publications in the requested window.")
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]), help="First publish date (inclusive).")
@click.option("--until", type=click.DateTime(formats=["%Y-%m-%d"]), help="Last publish date (inclusive).")
@click.option("--type", "--publication-type", "kind", type=click.Choice(("all", *_PUBLICATION_TYPES)),
              default="all", show_default=True, help="YouTube publication type to list.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
def channel_list(source: str, limit: int, since: datetime | None, until: datetime | None,
                 kind: youtube_api.PublicationType, as_json: bool) -> None:
    """List publications for a YouTube channel URL or @handle, newest first."""
    if since and until and since > until:
        raise click.UsageError("--since must be on or before --until.")
    try:
        channel = youtube_api.resolve_channel(source)
        if channel is None:
            raise click.BadParameter("Expected a YouTube channel URL or @handle.", param_hint="SOURCE")
        kinds = _PUBLICATION_TYPES if kind == "all" else (kind,)
        rows = _list_publications(
            channel.channel_id, kinds, limit, since.date() if since else None, until.date() if until else None,
        )
    except youtube_api.NotConfigured as exc:
        click.echo(str(exc), err=True)
        return
    except youtube_api.InvalidKey:
        raise click.ClickException(
            "YouTube API key rejected. Replace it with neurolearn config set-key youtube --from-file <path>."
        ) from None
    except youtube_api.QuotaExhausted:
        raise click.ClickException("YouTube Data API quota exhausted.") from None
    except youtube_api.NotFound as exc:
        raise click.ClickException(str(exc)) from None
    except youtube_api.YouTubeApiError as exc:
        raise click.ClickException(f"YouTube Data API request failed: {exc}") from None
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False))
        return
    table = Table("Title", "Published", "Type", "Duration (s)", "Views", "Likes", "Comments", box=None)
    for row in rows:
        counts = (row[key] for key in ("duration_sec", "view_count", "like_count", "comment_count"))
        table.add_row(
            Text(row["title"] or row["video_id"]), row["published_at"].split("T")[0],
            row["publication_type"], *("-" if value is None else str(value) for value in counts),
        )
    make_console().print(table)
