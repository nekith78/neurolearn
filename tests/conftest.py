"""Test-wide conftest.

Primes macOS dyld search path so test code that imports `weasyprint`
directly (rather than via the report package) can still find
Homebrew-installed pango/cairo/gobject. The report package does the
same priming on import, but standalone test imports go through
pytest.importorskip and don't touch the package.
"""
from __future__ import annotations

from skills.neurolearn.report._macos import prime_native_libs_for_weasyprint


prime_native_libs_for_weasyprint()
