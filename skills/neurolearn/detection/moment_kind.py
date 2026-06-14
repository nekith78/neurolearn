"""Classify a single visual moment as a *procedure* or a *showcase*.

Research on illustrated step-by-step guides is consistent: multi-step
PROCESSES (crafting, configuring, a sequence of UI actions) should be shown
densely — one screenshot per step — while a one-off REFERENCE/showcase (an
item, a panel, a result) needs a single clear image. So the report pipeline
needs to know which kind each moment is, to decide how many frames to capture
and how deeply to describe it.

This is a cheap, free, language-agnostic heuristic over the moment's
transcript context: a moment reads as a procedure when it stacks several
*action verbs* (reusing the tutorial detector's vocabulary) together with
*sequential connectives* ("then", "after", "next" / "потом", "затем",
"далее"). Deliberately domain-neutral — no game/app-specific words — so it
generalizes (cooking steps, software setup, crafting) per the "examples
illustrate, don't constrain" rule.
"""
from __future__ import annotations

import re

from skills.neurolearn.detection.tutorial_detect import _COMPILED_PATTERNS

SHOWCASE = "showcase"
PROCEDURE = "procedure"

# Sequential / step connectives — the tell that several actions form an
# ordered process rather than one standalone action.
_CONNECTIVE_PATTERNS = [
    r"\bthen\b", r"\bafter (that|this)\b", r"\bnext\b", r"\bfirst(ly)?\b",
    r"\bsecond(ly)?\b", r"\bthird(ly)?\b", r"\bfinally\b", r"\bonce you\b",
    r"\bfrom (here|there)\b", r"\bat this point\b", r"\bstep\b", r"\bafterwards?\b",
    r"\bпотом\b", r"\bзатем\b", r"\bдалее\b", r"\bсначала\b", r"\bпосле (этого|чего)\b",
    r"\bтеперь\b", r"\bв конце\b", r"\bна этом (этапе|шаге)\b", r"\bшаг\b",
]
_COMPILED_CONNECTIVES = [re.compile(p, re.IGNORECASE) for p in _CONNECTIVE_PATTERNS]


def _count(patterns, text: str) -> int:
    return sum(1 for p in patterns if p.search(text))


def classify_moment_kind(text: str) -> str:
    """Return ``"procedure"`` for a multi-step process worth a per-step visual
    breakdown, else ``"showcase"``. Based on action-verb density plus the
    presence of sequential connectives in the moment's transcript context."""
    if not text:
        return SHOWCASE
    actions = _count(_COMPILED_PATTERNS, text)
    connectives = _count(_COMPILED_CONNECTIVES, text)
    # Procedure if the narration is clearly stepwise. Three signals, any of:
    #  • dense sequential connectives ("first… then… until you… and then") —
    #    works even for domain crafts whose verbs aren't generic UI actions;
    #  • a couple of UI actions chained by a connective;
    #  • several UI actions stacked together.
    if connectives >= 3 or (actions >= 2 and connectives >= 1) or actions >= 3:
        return PROCEDURE
    return SHOWCASE
