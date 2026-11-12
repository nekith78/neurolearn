"""Fetch a YouTube comment sample and preserve its compact and structured forms."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from skills.neurolearn import youtube_api
from skills.neurolearn.utils.platform_errors import diagnose
from skills.neurolearn.utils.ytdlp import create_ytdlp
from skills.neurolearn.youtube_fallback import FallbackNotice, fallback_notice_for_run


class CommentsFetchError(Exception):
    """The site fallback could not provide a comment sample."""


@dataclass
class Comment:
    id: str
    author: str
    text: str
    like_count: int | None
    published_at: str | None
    is_channel_owner: bool
    reply_count: int | None = 0
    replies: list[Comment] = field(default_factory=list)


@dataclass
class CommentSample:
    video_id: str
    comments: list[Comment]
    total: int | None = None
    source: str = "api"
    order: str = "relevance"
    cap: int = youtube_api.DEFAULT_COMMENT_CAP
    approximate_fields: list[str] = field(default_factory=list)


def _parse_comment(item: dict, owner_id: str | None) -> Comment:
    snippet = item["snippet"]
    author_id = snippet.get("authorChannelId", {}).get("value")
    return Comment(
        id=item["id"],
        author=snippet.get("authorDisplayName", ""),
        text=snippet["textDisplay"],
        like_count=snippet.get("likeCount"),
        published_at=snippet.get("publishedAt"),
        is_channel_owner=bool(owner_id and author_id == owner_id),
    )


def _api_sample(video_id: str) -> CommentSample:
    """Fetch the default relevance sample, preserving YouTube's thread order."""
    threads = youtube_api.list_comment_threads(video_id)
    details = youtube_api.fetch_video_details([video_id]).get(video_id)
    comments = []
    try:
        for thread in threads:
            snippet = thread["snippet"]
            owner_id = (details.channel_id if details else None) or snippet.get("channelId")
            comment = _parse_comment(snippet["topLevelComment"], owner_id)
            comment.reply_count = snippet["totalReplyCount"]
            comment.replies = [
                _parse_comment(reply, owner_id)
                for reply in thread.get("replies", {}).get("comments", [])
            ]
            comments.append(comment)
    except (AttributeError, KeyError, TypeError):
        raise youtube_api.TransientFailure("Unexpected commentThreads.list response") from None
    total = details.comment_count if details else None
    return CommentSample(video_id=video_id, comments=comments, total=total)


def _yt_dlp_sample(video_id: str, cookies_file: str | Path | None) -> CommentSample:
    cap = youtube_api.DEFAULT_COMMENT_CAP
    options = {
        "quiet": True, "no_warnings": True, "skip_download": True, "getcomments": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {
            "comment_sort": ["top"],
            # yt-dlp has no inline-only replies mode. Avoid extra reply requests.
            "max_comments": [str(cap), str(cap), "0", "0", "1"],
        }},
    }
    if cookies_file:
        options["cookiefile"] = str(cookies_file)
    with create_ytdlp(options) as ydl:
        url = f"https://www.youtube.com/watch?v={video_id}"
        info = ydl.extract_info(url, download=False, process=False) or {}
        # post_extract replaces the video's total with the capped sample size.
        total = info.get("comment_count")
        ydl.post_extract(info)
    if "comments" not in info:
        raise CommentsFetchError("Could not fetch comments: yt-dlp returned no comments result.")
    if info["comments"] is None:
        raise youtube_api.CommentsDisabled("Comments are disabled for this video.")
    comments = []
    for item in info["comments"]:
        timestamp = item.get("timestamp")
        published_at = None
        if timestamp is not None:
            published_at = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        comments.append(Comment(
            id=item["id"], author=item.get("author") or "", text=item.get("text") or "",
            like_count=item.get("like_count"), published_at=published_at,
            is_channel_owner=bool(item.get("author_is_uploader")), reply_count=None,
        ))
    return CommentSample(
        video_id, comments, total=total, source="yt-dlp",
        approximate_fields=["like_count", "published_at"],
    )


def fetch_comments(
    video_id: str, *, notice: FallbackNotice | None = None, cookies_file: str | Path | None = None,
) -> CommentSample:
    """Prefer the API. Share a notice across videos in a batch."""
    try:
        return _api_sample(video_id)
    except (youtube_api.CommentsDisabled, youtube_api.NotFound):
        raise
    except youtube_api.YouTubeApiError as exc:
        (notice or fallback_notice_for_run()).report(exc)
    from yt_dlp.utils import YoutubeDLError

    cookie_path = None
    while True:
        try:
            return _yt_dlp_sample(video_id, cookie_path)
        except (YoutubeDLError, OSError) as exc:
            diagnosis = diagnose(str(exc), platform="youtube")
            if cookie_path or not cookies_file or not diagnosis.is_block:
                raise CommentsFetchError(f"Could not fetch comments: {diagnosis.raw_excerpt}") from None
            cookie_path = cookies_file


def _compact_line(comment: Comment) -> str:
    text = " ".join(comment.text.split())
    if len(text) > 300:
        text = text[:299] + "…"
    author = " ".join(comment.author.split())
    likes = comment.like_count if comment.like_count is not None else "?"
    marker = "owner" if comment.is_channel_owner else "-"
    return f"{likes} | {author} | {marker} | {text}"


def write_comments(sample: CommentSample, output_dir: Path, base_name: str) -> tuple[Path, Path]:
    """Write full JSON and a one-line-per-comment reading copy next to it."""
    fetched = len(sample.comments)
    total = sample.total if sample.total is not None else "unknown"
    lines = [
        f"# source={sample.source} order={sample.order} cap={sample.cap} "
        f"fetched={fetched} (top-level) total={total}"
    ]
    if sample.approximate_fields:
        lines[0] += f" approximate={','.join(sample.approximate_fields)}"
    for comment in sample.comments:
        lines.append(_compact_line(comment))
        lines.extend("  " + _compact_line(reply) for reply in comment.replies)

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / f"{base_name}.comments.txt"
    json_path = output_dir / f"{base_name}.comments.json"
    json_path.write_text(
        json.dumps({**asdict(sample), "fetched": fetched}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return text_path, json_path
