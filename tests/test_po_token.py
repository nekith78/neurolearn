"""Tests for utils.po_token readiness probe (shared by doctor + wizard)."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from skills.neurolearn.utils import po_token


@pytest.mark.parametrize("server_version, expected", [("2.0.2", True), ("1.3.1", False), (None, False)])
def test_status_requires_compatible_server_version(server_version, expected):
    with patch.object(po_token, "_node_version", return_value=(True, "v22.3.0", 22)), \
         patch.object(po_token, "plugin_version", return_value="2.0.2"), \
         patch.object(po_token, "server_reachable", return_value=True), \
         patch.object(po_token, "_server_version", return_value=server_version):
        st = po_token.status()
    assert st["node_ok"] is True
    assert st["po_token_server_reachable"] is True
    assert st["po_token_plugin_version"] == "2.0.2"
    assert st["po_token_server_version"] == server_version
    assert st["po_token_server_compatible"] is expected
    assert st["po_token_can_generate"] is expected


@pytest.mark.parametrize("body, status, expected", [
    (b'{"version":"2.0.2","server_uptime":5}', 200, "2.0.2"),
    (b'{"version":"1.3.1"}', 200, "1.3.1"),
    (b'{"version":"invalid"}', 200, None),
    (b'{"version":2}', 200, None),
    (b'[]', 200, None),
    (b'not JSON', 200, None),
    (b'{"version":"2.0.2"}', 302, None),
    (b'x' * 4097, 200, None),
])
def test_ping_validates_bounded_local_response(body, status, expected):
    response = Mock(status=status)
    response.read.return_value = body
    connection = Mock()
    connection.getresponse.return_value = response
    with patch.object(po_token.http.client, "HTTPConnection", return_value=connection) as factory:
        assert po_token._server_version() == expected
    factory.assert_called_once_with("127.0.0.1", 4416, timeout=0.5)
    connection.request.assert_called_once_with("GET", "/ping")
    connection.close.assert_called_once()
    if status == 200:
        response.read.assert_called_once_with(4097)


def test_ping_timeout_is_not_readiness():
    connection = Mock()
    connection.request.side_effect = TimeoutError
    with patch.object(po_token.http.client, "HTTPConnection", return_value=connection):
        assert po_token._server_version() is None
    connection.close.assert_called_once()


def test_status_false_when_server_down():
    with patch.object(po_token, "_node_version", return_value=(True, "v22.3.0", 22)), \
         patch.object(po_token, "plugin_version", return_value="2.0.2"), \
         patch.object(po_token, "server_reachable", return_value=False), \
         patch.object(po_token, "_server_version") as ping:
        st = po_token.status()
    ping.assert_not_called()
    assert st["po_token_server_reachable"] is False
    assert st["po_token_can_generate"] is False  # plugin alone isn't enough


def test_server_without_plugin_is_not_ready():
    with patch.object(po_token, "_node_version", return_value=(False, None, None)), \
         patch.object(po_token, "plugin_version", return_value=None), \
         patch.object(po_token, "server_reachable", return_value=True), \
         patch.object(po_token, "_server_version", return_value="2.0.2"):
        st = po_token.status()
    assert st["po_token_plugin_installed"] is False
    assert st["po_token_can_generate"] is False


def test_node_version_parsing():
    with patch("skills.neurolearn.utils.po_token.shutil.which", return_value="/usr/bin/node"):
        with patch("skills.neurolearn.utils.po_token.subprocess.run",
                   return_value=SimpleNamespace(stdout="v18.20.0\n")):
            assert po_token._node_version() == (True, "v18.20.0", 18)
        with patch("skills.neurolearn.utils.po_token.subprocess.run",
                   return_value=SimpleNamespace(stdout="v20.0.0\n")):
            ok, ver, major = po_token._node_version()
    assert major == 20


def test_status_rejects_node_20_for_current_provider():
    with patch.object(po_token, "_node_version", return_value=(True, "v20.19.0", 20)), \
         patch.object(po_token, "plugin_version", return_value="2.0.2"), \
         patch.object(po_token, "server_reachable", return_value=False):
        st = po_token.status()
    assert st["node_ok"] is False


def test_plugin_probe_does_not_accept_an_unrelated_ytdlp_plugin():
    with patch("skills.neurolearn.utils.po_token.importlib.metadata.version",
               side_effect=po_token.importlib.metadata.PackageNotFoundError):
        assert po_token.plugin_installed() is False


def test_node_absent():
    with patch("skills.neurolearn.utils.po_token.shutil.which", return_value=None):
        assert po_token._node_version() == (False, None, None)
