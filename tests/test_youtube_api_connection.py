"""The real transport below the usual test seam, against a local HTTP server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from skills.neurolearn import youtube_api


@pytest.fixture
def server():
    connections = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            connections.append(self.client_address)
            body = json.dumps({"key": self.headers.get("X-goog-api-key")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/videos", connections
    httpd.shutdown()
    httpd.server_close()


def test_consecutive_requests_share_one_connection(server):
    url, connections = server
    for _ in range(3):
        assert youtube_api._http_get(url, {"id": "x"}, {"X-goog-api-key": "k"}, 5) == (200, {"key": "k"})
    assert len(set(connections)) == 1


def test_a_failed_connect_is_retried_once_before_giving_up(monkeypatch, server):
    url, connections = server
    client = youtube_api._shared_client()
    real_get, attempts = client.get, []

    def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("connection refused")
        return real_get(*args, **kwargs)

    monkeypatch.setattr(client, "get", flaky)
    assert youtube_api._http_get(url, {}, {"X-goog-api-key": "k"}, 5)[0] == 200
    assert len(attempts) == 2 and len(connections) == 1

    attempts.clear()
    monkeypatch.setattr(client, "get", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(youtube_api.TransientFailure):
        youtube_api._http_get(url, {}, {"X-goog-api-key": "k"}, 5)


def test_a_failure_after_the_request_was_sent_is_not_retried(monkeypatch, server):
    url, _ = server
    client = youtube_api._shared_client()
    attempts = []

    def timeout(*args, **kwargs):
        attempts.append(1)
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(client, "get", timeout)
    with pytest.raises(youtube_api.TransientFailure):
        youtube_api._http_get(url, {}, {"X-goog-api-key": "k"}, 5)
    assert len(attempts) == 1
