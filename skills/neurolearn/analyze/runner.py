"""Send a fully-built prompt to one of the four LLM backends.

Thin wrapper over the existing _call_* helpers in quality/asr_corrector.py.
No retries; on exception returns empty string so the CLI layer can
translate that into exit code 4 with a friendly hint.
"""
from __future__ import annotations

from skills.neurolearn.quality.asr_corrector import (
    _call_gemini, _call_groq, _call_ollama, _call_openai,
)

# v0.12.0: "claude" removed (see feedback_no_anthropic_api). "groq"
# (llama-3.3-70b-versatile) is the new primary default — 14,400 RPD
# free tier vs Gemini 3.5-flash's 20 RPD.
_KNOWN = {"groq", "gemini", "openai", "ollama"}


def run_analysis(
    full_prompt: str,
    *,
    backend: str,
    api_key: str | None,
    ollama_model: str = "llama3.2:3b",
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Return LLM response text, or "" on failure / empty response."""
    if backend not in _KNOWN:
        raise ValueError(f"unknown backend: {backend!r}")

    try:
        if backend == "groq":
            return _call_groq(full_prompt, api_key or "")
        if backend == "gemini":
            return _call_gemini(full_prompt, api_key or "")
        if backend == "openai":
            return _call_openai(full_prompt, api_key or "")
        if backend == "ollama":
            return _call_ollama(
                full_prompt, model=ollama_model, host=ollama_host,
            )
    except Exception:
        return ""
    return ""
