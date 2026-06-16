"""DetectionWindow + Detector Protocol."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DetectionWindow:
    start: float       # seconds
    end: float
    reason: str        # "raw" | "strict:ru" | "soft:ru" | "universal" | "scene_change"
    score: float       # 0..1
    weight: float = 1.0
    phrase: str = ""   # the phrase that fired (for trigger-windows)
    transcript_context: str = ""   # surrounding transcript text — the
    # vision model's PRIMARY grounding (what the speaker says around this
    # moment), so it describes the on-screen content the speaker refers to
    # rather than guessing blind. Populated just before annotation.

    @property
    def priority_score(self) -> float:
        return self.score * self.weight


class Detector(Protocol):
    """Anything that finds visual-important windows in a video."""

    def find_windows(
        self,
        segments: list,
        video_path: Path | None,
        triggers,           # TriggerConfig
    ) -> list[DetectionWindow]:
        ...
