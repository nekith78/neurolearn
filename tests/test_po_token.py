"""Tests for utils.po_token readiness probe (shared by doctor + wizard)."""
from types import SimpleNamespace
from unittest.mock import patch

from skills.neurolearn.utils import po_token


def test_status_can_generate_when_plugin_and_server():
    with patch.object(po_token, "_node_version", return_value=(True, "v22.3.0", 22)), \
         patch.object(po_token, "plugin_installed", return_value=True), \
         patch.object(po_token, "server_reachable", return_value=True):
        st = po_token.status()
    assert st["node_ok"] is True
    assert st["po_token_can_generate"] is True


def test_status_false_when_server_down():
    with patch.object(po_token, "_node_version", return_value=(True, "v22.3.0", 22)), \
         patch.object(po_token, "plugin_installed", return_value=True), \
         patch.object(po_token, "server_reachable", return_value=False):
        st = po_token.status()
    assert st["po_token_server_reachable"] is False
    assert st["po_token_can_generate"] is False  # plugin alone isn't enough


def test_node_ok_requires_major_20():
    with patch("skills.neurolearn.utils.po_token.shutil.which", return_value="/usr/bin/node"):
        with patch("skills.neurolearn.utils.po_token.subprocess.run",
                   return_value=SimpleNamespace(stdout="v18.20.0\n")):
            assert po_token._node_version() == (True, "v18.20.0", 18)
        with patch("skills.neurolearn.utils.po_token.subprocess.run",
                   return_value=SimpleNamespace(stdout="v20.0.0\n")):
            ok, ver, major = po_token._node_version()
    assert major == 20


def test_node_absent():
    with patch("skills.neurolearn.utils.po_token.shutil.which", return_value=None):
        assert po_token._node_version() == (False, None, None)
