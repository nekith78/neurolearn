"""Memory-file storage layer — CRUD on Markdown files with YAML frontmatter.

A memory file looks like:

    ---
    name: claude-tips
    description: |
      Curated tips and tricks for Claude Code. Hooks, skills, MCP,
      slash commands. Only user-approved findings.
    created: 2026-05-26T03:14:15+00:00
    sources: 12
    last_updated: 2026-05-26T03:14:15+00:00
    ---

    ## 2026-05-26 — Topic title
    - Fact 1
    - Fact 2

    Source: <url> | 03:12-04:05
    Approved: 2026-05-26

The frontmatter is parsed via the stdlib (PyYAML isn't a dep). We
accept the simple `key: value` shapes neurolearn writes; we do NOT
try to support arbitrary YAML — keeps the file format predictable
and lets us hand-edit without tooling.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from skills.neurolearn.config import CONFIG_DIR, Config


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class MemoryFile:
    """In-memory representation of a memory .md file."""
    name: str
    description: str = ""
    created: str = ""        # ISO-8601 timestamp
    last_updated: str = ""
    sources: int = 0         # how many videos have contributed
    body: str = ""           # everything after the frontmatter

    def to_markdown(self) -> str:
        """Serialize back to disk-format Markdown with frontmatter."""
        desc_block = self.description.strip()
        if "\n" in desc_block:
            # Multi-line description → use literal block scalar
            indented = "\n".join("  " + line for line in desc_block.splitlines())
            desc_field = f"description: |\n{indented}"
        elif desc_block:
            # Single-line with quotes to avoid YAML special-char surprises
            esc = desc_block.replace('"', '\\"')
            desc_field = f'description: "{esc}"'
        else:
            desc_field = 'description: ""'

        lines = [
            "---",
            f"name: {self.name}",
            desc_field,
            f"created: {self.created or _now_iso()}",
            f"sources: {self.sources}",
            f"last_updated: {self.last_updated or _now_iso()}",
            "---",
            "",
            self.body.lstrip("\n"),
        ]
        return "\n".join(lines).rstrip() + "\n"


def memories_dir(cfg: Config | None = None) -> Path:
    """Resolve where memory files live."""
    if cfg is not None and cfg.memories_dir:
        return Path(cfg.memories_dir).expanduser()
    return CONFIG_DIR / "memories"


def memory_path(name: str, *, cfg: Config | None = None) -> Path:
    """Full path to a memory file. Doesn't have to exist."""
    safe_name = _slugify(name)
    return memories_dir(cfg) / f"{safe_name}.md"


def list_memories(*, cfg: Config | None = None) -> list[MemoryFile]:
    """Enumerate all memory files in the storage dir."""
    d = memories_dir(cfg)
    if not d.exists():
        return []
    out: list[MemoryFile] = []
    for p in sorted(d.glob("*.md")):
        try:
            out.append(read_memory(p.stem, cfg=cfg))
        except (OSError, ValueError):
            continue
    return out


def read_memory(name: str, *, cfg: Config | None = None) -> MemoryFile:
    """Load a memory file by name. Raises FileNotFoundError when absent."""
    p = memory_path(name, cfg=cfg)
    if not p.exists():
        raise FileNotFoundError(f"Memory file not found: {p}")
    text = p.read_text(encoding="utf-8")
    return parse_memory(text, fallback_name=_slugify(name))


def write_memory(memory: MemoryFile, *, cfg: Config | None = None) -> Path:
    """Atomically write a memory file to disk. Returns the path."""
    d = memories_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    p = memory_path(memory.name, cfg=cfg)
    # Update last_updated on every write
    memory.last_updated = _now_iso()
    if not memory.created:
        memory.created = memory.last_updated
    # Atomic write: temp file + rename
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(memory.to_markdown(), encoding="utf-8")
    tmp.replace(p)
    return p


def delete_memory(name: str, *, cfg: Config | None = None) -> Path:
    """Delete the memory file. Returns the deleted path."""
    p = memory_path(name, cfg=cfg)
    if not p.exists():
        raise FileNotFoundError(f"Memory file not found: {p}")
    p.unlink()
    return p


def rename_memory(old: str, new: str, *, cfg: Config | None = None) -> Path:
    """Rename a memory file. Updates the `name:` frontmatter field too.
    Returns the new path."""
    old_path = memory_path(old, cfg=cfg)
    if not old_path.exists():
        raise FileNotFoundError(f"Memory file not found: {old_path}")
    new_path = memory_path(new, cfg=cfg)
    if new_path.exists() and new_path != old_path:
        raise FileExistsError(f"Target memory already exists: {new_path}")
    memory = read_memory(old, cfg=cfg)
    memory.name = _slugify(new)
    write_memory(memory, cfg=cfg)
    # write_memory wrote to new_path (resolves from memory.name);
    # delete the old file unless it ended up being the same path.
    if old_path != memory_path(memory.name, cfg=cfg) and old_path.exists():
        old_path.unlink()
    return memory_path(memory.name, cfg=cfg)


def parse_memory(text: str, *, fallback_name: str = "") -> MemoryFile:
    """Parse the disk format back into a MemoryFile."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        # No frontmatter — treat everything as body
        return MemoryFile(name=fallback_name, body=text.strip())
    fm_text = m.group(1)
    body = text[m.end():].lstrip("\n")
    meta = _parse_simple_yaml(fm_text)
    return MemoryFile(
        name=meta.get("name", fallback_name),
        description=meta.get("description", ""),
        created=meta.get("created", ""),
        last_updated=meta.get("last_updated", ""),
        sources=int(meta.get("sources", 0) or 0),
        body=body,
    )


def append_facts_to_body(
    memory: MemoryFile,
    facts: list[dict],
    source_url: str,
    when: str | None = None,
) -> None:
    """Append a new section to the body with one bullet per approved fact.

    `facts` shape:
      [{"text": "...", "source_timestamp": "12:30-13:45" or None,
        "topic": "Hooks" or None}, ...]
    """
    if not facts:
        return
    date_str = (when or _now_iso())[:10]   # YYYY-MM-DD
    # Group facts by topic if topics are provided
    by_topic: dict[str, list[dict]] = {}
    for f in facts:
        topic = (f.get("topic") or "Notes").strip() or "Notes"
        by_topic.setdefault(topic, []).append(f)

    new_sections: list[str] = []
    for topic, items in by_topic.items():
        section_lines = [f"## {date_str} — {topic}"]
        for f in items:
            section_lines.append(f"- {f['text']}")
        ts = items[0].get("source_timestamp")
        ts_part = f" | {ts}" if ts else ""
        section_lines.append(f"")
        section_lines.append(f"Source: {source_url}{ts_part}")
        section_lines.append(f"Approved: {date_str}")
        section_lines.append("")
        new_sections.append("\n".join(section_lines))

    appended = "\n".join(new_sections)
    if memory.body.strip():
        memory.body = appended + "\n" + memory.body
    else:
        memory.body = appended
    memory.sources += 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9\-]+")
_MULTI_DASH_RE = re.compile(r"-{2,}")


def _slugify(name: str) -> str:
    """Memory names are stored as `<slug>.md` on disk. Keep ASCII, lowercase,
    hyphen-separated. Lets users pass either 'claude tips' or 'claude-tips'."""
    s = (name or "").strip().lower()
    s = s.replace("_", "-").replace(" ", "-")
    s = _SLUG_RE.sub("", s)
    # Collapse runs of hyphens — "tips & notes" → "tips - notes" → "tips--notes" → "tips-notes"
    s = _MULTI_DASH_RE.sub("-", s)
    s = s.strip("-")
    return s or "memory"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_simple_yaml(text: str) -> dict:
    """Parse the subset of YAML neurolearn writes (key: value, with `|`
    literal blocks for multi-line strings). NOT a full YAML parser."""
    result: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "|":
            # Block scalar — gather indented lines that follow
            block_lines: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                if lines[i].strip():
                    block_lines.append(lines[i][2:])
                else:
                    block_lines.append("")
                i += 1
            result[key] = "\n".join(block_lines).strip()
            continue
        # Strip surrounding quotes if present
        if (rest.startswith('"') and rest.endswith('"')) or \
           (rest.startswith("'") and rest.endswith("'")):
            rest = rest[1:-1].replace('\\"', '"')
        result[key] = rest
        i += 1
    return result
