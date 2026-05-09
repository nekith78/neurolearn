#!/usr/bin/env bash
# install.sh — bootstrap installer for macOS/Linux
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Checking ffmpeg..."
if ! command -v ffmpeg >/dev/null 2>&1; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew >/dev/null 2>&1; then
            brew install ffmpeg
        else
            echo "WARNING: ffmpeg not found and Homebrew not installed."
            echo "Install ffmpeg manually before transcribing."
        fi
    else
        echo "WARNING: ffmpeg not found. Install via your package manager (apt, dnf, pacman)."
    fi
fi

echo "==> Syncing dependencies..."
uv sync

echo "==> Running wizard..."
uv run youtube-transcribe config wizard

echo "==> Done!"
echo "Try: uv run youtube-transcribe transcribe https://youtu.be/<id>"
