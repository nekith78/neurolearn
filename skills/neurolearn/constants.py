"""Shared default constants — single source of truth.

Leaf module (no project imports) so any module can import it without
risk of a circular import.
"""
from __future__ import annotations

# Default local Ollama model + host used by every analyze / filter /
# summarize / translate / ASR-correction path. Bump here once instead of
# editing the literal across ~14 files.
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
