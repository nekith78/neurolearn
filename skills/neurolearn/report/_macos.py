"""macOS dyld-path priming for WeasyPrint native libraries.

WeasyPrint's `import` triggers dlopen on libgobject/libpango/libcairo.
On Apple Silicon Homebrew installs these under `/opt/homebrew/lib`
(Intel: `/usr/local/lib`) which is NOT on the default dyld search
path. Without intervention, `import weasyprint` raises OSError on
stock Pythons (uv, system, pyenv-managed) even when the brew libs
are installed.

`DYLD_FALLBACK_LIBRARY_PATH` is honored by dyld at each `dlopen`
call (not only at process start — that's the difference from
`DYLD_LIBRARY_PATH`), so mutating `os.environ` in-process *before*
the first weasyprint import works on stock macOS.

This module is a no-op on non-Darwin and when the brew prefix dirs
don't exist (i.e. the user installed pango via apt/conda/nix).
"""
from __future__ import annotations

import os
import platform

_BREW_LIB_PREFIXES = ("/opt/homebrew/lib", "/usr/local/lib")


def prime_native_libs_for_weasyprint() -> None:
    """Prepend brew lib dirs to DYLD_FALLBACK_LIBRARY_PATH.

    Idempotent — if the dir is already in the env var, do nothing.
    Safe to call multiple times.
    """
    if platform.system() != "Darwin":
        return
    for brew_lib in _BREW_LIB_PREFIXES:
        if not os.path.isdir(brew_lib):
            continue
        existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        if brew_lib in existing.split(":"):
            continue
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            brew_lib + (":" + existing if existing else "")
        )
