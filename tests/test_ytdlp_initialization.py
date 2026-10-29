"""Parallel metadata probes must not register yt-dlp plugins twice."""
import subprocess
import sys


def test_parallel_ytdlp_initialization_registers_plugins_once():
    # Fresh interpreter: other tests may already have initialized yt-dlp.
    # Only constructors run; no URL, extraction, or network call is involved.
    result = subprocess.run(
        [sys.executable, "-c", '''
import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from skills.neurolearn.utils.ytdlp import create_ytdlp

module = importlib.import_module("yt_dlp.YoutubeDL")
original = module.load_all_plugins
calls = []
start = threading.Barrier(2)

def delayed_load():
    calls.append(True)
    # Widen the race where a second constructor sees plugins as not loaded.
    time.sleep(0.1)
    original()

module.load_all_plugins = delayed_load

def construct(_):
    start.wait(timeout=5)
    with create_ytdlp({"quiet": True}) as ydl:
        # Both contexts must overlap: the lock must not cover extraction.
        start.wait(timeout=5)

with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(construct, range(2)))
assert len(calls) == 1, calls
'''],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "already registered" not in result.stderr
