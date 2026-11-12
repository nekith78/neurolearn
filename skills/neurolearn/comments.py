"""Fetch a YouTube comment sample and preserve its compact and structured forms."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from skills.neurolearn import youtube_api


@dataclass
class Comment:
    id: str
    author: str
    text: str
    like_count: int | None
    published_at: str | None
    is_channel_owner: bool
    reply_count: int = 0
    replies: list[Comment] = field(default_factory=list)


@dataclass
class CommentSample:
    video_id: str
    comments: list[Comment]
    total: int | None = None
    source: str = "api"
    order: str = "relevance"
    cap: int = youtube_api.DEFAULT_COMMENT_CAP


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


def fetch_comments(video_id: str) -> CommentSample:
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
