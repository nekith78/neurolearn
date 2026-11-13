"""Fetch a YouTube comment sample and preserve its compact and structured forms."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from skills.neurolearn import youtube_api
from skills.neurolearn.utils.files import atomic_write_text, read_regular_text
from skills.neurolearn.utils.platform_errors import diagnose
from skills.neurolearn.utils.ytdlp import create_ytdlp
from skills.neurolearn.youtube_fallback import FallbackNotice, fallback_notice_for_run


class CommentsFetchError(Exception):
    """The site fallback could not provide a comment sample."""


@dataclass(frozen=True)
class CommentOptions:
    cap: int | None = None
    order: str = "relevance"
    full_replies: bool = False
    markers: bool = False


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
    is_pinned: bool | None = None
    creator_heart: bool | None = None
    parent_id: str | None = None


@dataclass
class CommentSample:
    video_id: str
    comments: list[Comment]
    total: int | None = None
    source: str = "api"
    order: str = "relevance"
    cap: int = youtube_api.DEFAULT_COMMENT_CAP
    approximate_fields: list[str] = field(default_factory=list)
    replies_mode: str = "inline"
    markers: str = "off"
    notes: list[str] = field(default_factory=list)
    requested_options: CommentOptions = field(default_factory=CommentOptions)


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
        parent_id=snippet.get("parentId"),
    )


def _api_sample(video_id: str, options: CommentOptions, total: int | None = None) -> CommentSample:
    """Fetch threads in their source order before any local sorting.

    A caller that already knows the video's comment total passes it and
    saves the details request; each thread names the video's channel.
    """
    api_order = "time" if options.order == "newest" else "relevance"
    threads = youtube_api.list_comment_threads(video_id, cap=options.cap, order=api_order)
    details = None
    if total is None:
        details = youtube_api.fetch_video_details([video_id]).get(video_id)
        total = details.comment_count if details else None
    sample = CommentSample(video_id, [], total=total,
                           replies_mode="full" if options.full_replies else "inline")
    try:
        for thread in threads:
            snippet = thread["snippet"]
            owner_id = (details.channel_id if details else None) or snippet.get("channelId")
            comment = _parse_comment(snippet["topLevelComment"], owner_id)
            comment.reply_count = snippet["totalReplyCount"]
            replies = thread.get("replies", {}).get("comments", [])
            if options.full_replies and len(replies) < comment.reply_count:
                try:
                    replies = youtube_api.list_comment_replies(comment.id)
                except youtube_api.NotFound:
                    # A thread can be deleted between the thread and reply requests.
                    pass
                if len(replies) < comment.reply_count:
                    sample.replies_mode = "partial"
            comment.replies = [_parse_comment(reply, owner_id) for reply in replies]
            sample.comments.append(comment)
    except (AttributeError, KeyError, TypeError):
        raise youtube_api.TransientFailure("Unexpected commentThreads.list response") from None
    if sample.replies_mode == "partial":
        sample.notes.append("The API returned fewer public replies than the reported thread count.")
    return sample


def _yt_dlp_sample(
    video_id: str, cookies_file: str | Path | None, options: CommentOptions,
    marker_reply_budget: int | None = None,
) -> CommentSample:
    cap = options.cap if options.cap is not None else youtube_api.DEFAULT_COMMENT_CAP
    # The newest feed can put one older pinned thread before its chronological results.
    parent_budget = cap + 1 if options.order == "newest" else cap
    # With no published total, allow one sample's worth of replies and report truncation.
    reply_budget = cap if options.full_replies else 0
    if marker_reply_budget is not None:
        reply_budget = marker_reply_budget

    def limits_for(replies: int) -> list[str]:
        # Total, parents, replies, replies per thread, depth (including the parent).
        return list(map(str, (parent_budget + replies, parent_budget, replies, replies, 1 + replies)))

    limits = limits_for(reply_budget)
    ydl_options = {
        "quiet": True, "no_warnings": True, "skip_download": True, "getcomments": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {
            "comment_sort": ["new" if options.order == "newest" else "top"],
            "max_comments": limits,
        }},
    }
    if cookies_file:
        ydl_options["cookiefile"] = str(cookies_file)
    with create_ytdlp(ydl_options) as ydl:
        url = f"https://www.youtube.com/watch?v={video_id}"
        info = ydl.extract_info(url, download=False, process=False) or {}
        # Comments are fetched lazily by post_extract; remember the video's total before
        # it is replaced with the sample size. Use that finite bound for full replies.
        total = info.get("comment_count")
        if options.full_replies and marker_reply_budget is None and isinstance(total, int):
            reply_budget = max(cap, total)
            limits[:] = limits_for(reply_budget)
        ydl.post_extract(info)
    if "comments" not in info:
        raise CommentsFetchError("Could not fetch comments: yt-dlp returned no comments result.")
    if info["comments"] is None:
        raise youtube_api.CommentsDisabled("Comments are disabled for this video.")
    parents = {}
    replies = []
    for item in info["comments"]:
        timestamp = item.get("timestamp")
        published_at = None
        if timestamp is not None:
            published_at = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        comment = Comment(
            id=item["id"], author=item.get("author") or "", text=item.get("text") or "",
            like_count=item.get("like_count"), published_at=published_at,
            is_channel_owner=bool(item.get("author_is_uploader")), reply_count=None,
            is_pinned=item.get("is_pinned") if options.markers else None,
            creator_heart=item.get("is_favorited") if options.markers else None,
        )
        parent_id = item.get("parent")
        if not parent_id or parent_id == "root":
            if len(parents) < parent_budget:
                parents[comment.id] = comment
        elif reply_budget:
            replies.append((parent_id, comment))
    # yt-dlp emits thread ancestors before their children. Keep source order and the
    # immediate parent ID, including replies to other replies in the same thread.
    roots = dict(parents)
    for parent_id, reply in replies:
        root = roots.get(parent_id)
        if root is not None:
            reply.parent_id = parent_id
            root.replies.append(reply)
            roots[reply.id] = root
    selected = list(parents.values())
    if options.order == "newest":
        selected.sort(key=lambda comment: comment.published_at or "", reverse=True)
        selected = selected[:cap]
    sample = CommentSample(
        video_id, selected, total=total, source="yt-dlp",
        approximate_fields=["like_count", "published_at"],
        replies_mode="full" if options.full_replies else "none",
        markers="yt-dlp" if options.markers else "off",
    )
    if options.markers and any(
        row.is_pinned is None or row.creator_heart is None
        for parent in sample.comments for row in (parent, *parent.replies)
    ):
        sample.markers = "partial"
        sample.notes.append("yt-dlp did not supply all markers.")
    if not options.full_replies:
        sample.notes.append("yt-dlp does not supply inline replies.")
    elif info.get("comment_count") is None:
        sample.replies_mode = "partial"
        sample.notes.append("Site comment extraction was interrupted.")
    elif len(replies) >= reply_budget:
        sample.replies_mode = "bounded"
        sample.notes.append(f"Reached the site reply limit ({reply_budget}); threads may be incomplete.")
    return sample


def _apply_order(sample: CommentSample, options: CommentOptions) -> CommentSample:
    sample.requested_options = options
    sample.cap = options.cap if options.cap is not None else youtube_api.DEFAULT_COMMENT_CAP
    sample.order = options.order
    if options.order == "likes":
        sample.notes.append("Likes are sorted within the fetched relevance sample.")
        sample.comments.sort(key=lambda comment: comment.like_count if comment.like_count is not None else -1,
                             reverse=True)
    return sample


def _site_sample(
    video_id: str, options: CommentOptions, cookies_file: str | Path | None,
    marker_reply_budget: int | None = None,
) -> CommentSample:
    from yt_dlp.utils import YoutubeDLError

    cookie_path = None
    while True:
        try:
            return _yt_dlp_sample(video_id, cookie_path, options, marker_reply_budget)
        except (YoutubeDLError, OSError) as exc:
            diagnosis = diagnose(str(exc), platform="youtube")
            if cookie_path or not cookies_file or not diagnosis.is_block:
                raise CommentsFetchError(f"Could not fetch comments: {diagnosis.raw_excerpt}") from None
            cookie_path = cookies_file
        except (ValueError, OverflowError, KeyError, TypeError) as exc:
            raise CommentsFetchError(f"Invalid yt-dlp comments response ({type(exc).__name__}).") from None


def _merge_markers(sample: CommentSample, options: CommentOptions, cookies_file: str | Path | None) -> None:
    lookup_budget = sum(len(parent.replies) for parent in sample.comments)
    try:
        site = _site_sample(sample.video_id, options, cookies_file, marker_reply_budget=lookup_budget)
    except (CommentsFetchError, youtube_api.YouTubeApiError) as exc:
        sample.markers = "unavailable"
        sample.notes.append(f"Site markers unavailable: {exc}")
        return
    by_id = {row.id: row for parent in site.comments for row in (parent, *parent.replies)}
    sample.markers = "yt-dlp"
    for parent in sample.comments:
        for row in (parent, *parent.replies):
            match = by_id.get(row.id)
            if match is not None:
                row.is_pinned, row.creator_heart = match.is_pinned, match.creator_heart
            if row.is_pinned is None or row.creator_heart is None:
                sample.markers = "partial"
    if sample.markers == "partial":
        sample.notes.append("The capped site lookup did not supply all markers.")


def fetch_comments(
    video_id: str, *, options: CommentOptions = CommentOptions(),
    notice: FallbackNotice | None = None, cookies_file: str | Path | None = None,
    total: int | None = None,
) -> CommentSample:
    """Prefer the API. Share a notice across videos in a batch."""
    try:
        sample = _api_sample(video_id, options, total)
    except (youtube_api.CommentsDisabled, youtube_api.NotFound):
        raise
    except youtube_api.YouTubeApiError as exc:
        (notice or fallback_notice_for_run()).report(exc)
        sample = _site_sample(video_id, options, cookies_file)
    else:
        if options.markers and sample.comments:
            _merge_markers(sample, options, cookies_file)
    return _apply_order(sample, options)


def _compact_line(comment: Comment) -> str:
    text = " ".join(comment.text.split())
    if len(text) > 300:
        text = text[:299] + "…"
    author = " ".join(comment.author.split())
    likes = comment.like_count if comment.like_count is not None else "?"
    markers = [name for name, present in (("owner", comment.is_channel_owner),
                                          ("pinned", comment.is_pinned), ("creator-heart", comment.creator_heart))
               if present]
    marker = ",".join(markers) or "-"
    return f"{likes} | {author} | {marker} | {text}"


def write_comments(sample: CommentSample, output_dir: Path, base_name: str) -> tuple[Path, Path]:
    """Write full JSON and a one-line-per-comment reading copy next to it."""
    fetched = len(sample.comments)
    total = sample.total if sample.total is not None else "unknown"
    lines = [
        f"# source={sample.source} order={sample.order} cap={sample.cap} "
        f"fetched={fetched} (top-level) total={total} replies={sample.replies_mode} markers={sample.markers}"
    ]
    if sample.approximate_fields:
        lines[0] += f" approximate={','.join(sample.approximate_fields)}"
    if sample.notes:
        lines[0] += " — " + " ".join(sample.notes)
    for comment in sample.comments:
        lines.append(_compact_line(comment))
        lines.extend("  " + _compact_line(reply) for reply in comment.replies)

    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / f"{base_name}.comments.txt"
    json_path = output_dir / f"{base_name}.comments.json"
    compact = ("\n".join(lines) + "\n").replace("\r\n", "\n").replace("\r", "\n")
    record = {**asdict(sample), "fetched": fetched,
              "compact_sha256": hashlib.sha256(compact.encode("utf-8")).hexdigest()}
    atomic_write_text(json_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(text_path, compact)
    return text_path, json_path


def read_cached_comments(
    transcript: Path, options: CommentOptions | None = None, *, require_json: bool = False,
) -> str | None:
    """Return the checked text snapshot, including legacy hand-supplied text samples."""
    try:
        compact = read_regular_text(transcript.with_suffix(".comments.txt"))
        try:
            record = json.loads(read_regular_text(transcript.with_suffix(".comments.json")))
        except FileNotFoundError:
            return compact if options is None and not require_json else None
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    if options is not None and record.get("requested_options") != asdict(options):
        return None
    if "compact_sha256" in record:
        if record["compact_sha256"] != hashlib.sha256(compact.encode("utf-8")).hexdigest():
            return None
    elif options is not None or "requested_options" in record:
        # Old generated records with options cannot attest to the text file they accompany.
        return None
    return compact
