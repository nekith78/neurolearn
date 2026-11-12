"""Daily local accounting for YouTube Data API reads."""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from skills.neurolearn.config import Config


def _pacific_day() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


class QuotaStateError(Exception):
    """The local counter cannot safely account for a request."""


class DailyQuota:
    def __init__(self, config_dir: Path, cfg: Config):
        self.path = config_dir / "youtube-quota.sqlite3"
        self.limits = {"general": cfg.youtube_daily_units, "search": cfg.youtube_daily_searches}
        for setting in ("daily_units", "daily_searches"):
            limit = getattr(cfg, f"youtube_{setting}")
            if type(limit) is not int or limit < 0:
                raise QuotaStateError(f"YouTube quota setting {setting} must be a nonnegative integer.")

    @contextmanager
    def _database(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path)) as db, db:
                yield db
        except (sqlite3.Error, OSError) as exc:
            raise QuotaStateError(f"YouTube quota database unavailable: {exc}") from exc

    def charge(self, bucket: str) -> str | None:
        """Reserve one request under the writer lock. The returned day owns its response."""
        with self._database() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS usage (day TEXT, bucket TEXT, "
                "used INTEGER NOT NULL, blocked INTEGER NOT NULL DEFAULT 0, "
                "PRIMARY KEY (day, bucket))"
            )
            day = _pacific_day()
            row = db.execute(
                "SELECT used, blocked FROM usage WHERE day = ? AND bucket = ?", (day, bucket)
            ).fetchone()
            used, blocked = row or (0, False)
            if blocked or used >= self.limits[bucket]:
                return None
            db.execute(
                "INSERT INTO usage(day, bucket, used) VALUES (?, ?, 1) "
                "ON CONFLICT(day, bucket) DO UPDATE SET used = used + 1", (day, bucket)
            )
        return day

    def mark_exhausted(self, day: str, bucket: str) -> None:
        with self._database() as db:
            db.execute("UPDATE usage SET blocked = 1 WHERE day = ? AND bucket = ?", (day, bucket))

    def snapshot(self) -> dict:
        day = _pacific_day()
        usage = {}
        if self.path.exists():
            with self._database() as db:
                # A first writer may have opened the file but not committed its table yet.
                if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'usage'").fetchone():
                    rows = db.execute("SELECT bucket, used, blocked FROM usage WHERE day = ?", (day,))
                    usage = {bucket: (used, blocked) for bucket, used, blocked in rows}
        result = {"day": day}
        for bucket, limit in self.limits.items():
            used, blocked = usage.get(bucket, (0, False))
            result[bucket] = {"used": used, "limit": limit, "exhausted": bool(blocked or used >= limit)}
        return result
