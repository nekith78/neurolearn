"""PO Token (bgutil) readiness probe — shared by `doctor` and the setup wizard.

The bgutil-ytdlp-pot-provider PIP plugin auto-registers with yt-dlp, but a
PO Token is only actually minted when a PROVIDER is running — most reliably
the bgutil HTTP server on 127.0.0.1:4416. Node presence alone is NOT enough
(the pre-v0.18.1 check conflated them). This module reports the honest
readiness so both the doctor JSON and the wizard can branch on it.

Setup paths:
  - Docker (no local Node needed): DOCKER_RUN_CMD below.
  - npx (needs Node >= 20):        NPX_RUN_CMD below.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import socket
import subprocess

POT_SERVER_HOST = "127.0.0.1"
POT_SERVER_PORT = 4416
NODE_MIN_MAJOR = 20  # bgutil-ytdlp-pot-provider 1.3+ requires Node >= 20

DOCKER_RUN_CMD = (
    "docker run --name bgutil-provider -d --init --restart unless-stopped "
    "-p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider"
)
NPX_RUN_CMD = "npx --yes bgutil-ytdlp-pot-provider  # needs Node >= 20"


def _node_version() -> tuple[bool, str | None, int | None]:
    """Return (node_available, version_string, major_int)."""
    if not shutil.which("node"):
        return False, None, None
    try:
        out = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5,
        )
        ver = (out.stdout or "").strip() or None
        m = re.search(r"v?(\d+)", ver or "")
        return True, ver, (int(m.group(1)) if m else None)
    except Exception:
        return True, None, None


def plugin_installed() -> bool:
    try:
        return bool(importlib.util.find_spec("yt_dlp_plugins"))
    except Exception:
        return False


def server_reachable(
    host: str = POT_SERVER_HOST, port: int = POT_SERVER_PORT, *, timeout: float = 0.3,
) -> bool:
    """True when a provider is listening on the bgutil port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def status() -> dict:
    """Honest PO Token readiness snapshot for doctor / wizard."""
    node_available, node_version, node_major = _node_version()
    node_ok = node_major is not None and node_major >= NODE_MIN_MAJOR
    plugin = plugin_installed()
    reachable = server_reachable()
    return {
        "node_available": node_available,
        "node_version": node_version,
        "node_ok": node_ok,  # Node >= NODE_MIN_MAJOR
        "po_token_plugin_installed": plugin,
        "po_token_server_reachable": reachable,
        # A token only mints when the plugin shim AND a reachable provider
        # are both present. Node alone is not sufficient.
        "po_token_can_generate": plugin and reachable,
    }
