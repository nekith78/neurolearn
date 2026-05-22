# neurolearn demo tape — README hero GIF.
#
# Regenerate with:
#   brew install vhs      # one-time
#   vhs assets/demo.tape  # produces assets/demo.gif (deterministic)
#
# No network calls. Uses the bundled qa-out/v0101-smoke batch and a
# pre-recorded demo log so the GIF is reproducible from a clean checkout.
#
# Lessons baked in from previous tape iterations:
#   * Pure ASCII in every `Type "..."` string. Em-dash, middle dot, etc.
#     get mangled by some terminals into multi-byte escape sequences
#     that swallow surrounding characters.
#   * Typing speed = 70ms. Faster looks impressive but vhs drops the
#     leading characters of fast Type commands.
#   * One command per Type, no `&&` chains.
#   * Never run anything that prints API-key fragments. `config show`
#     and `config get gemini-key` are banned from public GIFs.
#   * Long-running commands (transcribe, batch, research, vhs build
#     itself can stall) are SHOWN as typed commands then cleared, with
#     a pre-recorded log cat'd for the actual output proof. Real-time
#     network transcribe is impossible to record deterministically.

Output assets/demo.gif

Set FontSize 14
Set Width 1100
Set Height 760
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 70ms
Set PlaybackSpeed 1.0

# Hidden setup. vhs runs in a non-interactive shell that doesn't load
# ~/.zshrc — the project venv binary isn't on PATH unless we put it
# there manually.
Hide
Type "export PATH=$PWD/.venv/bin:$PATH"
Enter
Sleep 200ms
Type "clear"
Enter
Sleep 500ms
Show

# ---- Beat 1: top-level surface ----
Type "neurolearn --help"
Sleep 400ms
Enter
Sleep 4500ms

# ---- Beat 2: one-time setup ----
Type "clear"
Enter
Sleep 300ms
Type "# one-time setup: pick backends + register API keys"
Sleep 300ms
Enter
Sleep 400ms
Type "neurolearn config --help"
Sleep 400ms
Enter
Sleep 4500ms

# ---- Beat 3: transcribe a video (typed command, cached output) ----
Type "clear"
Enter
Sleep 300ms
Type "# transcribe a YouTube video - auto-handles size limits + hallucinations"
Sleep 300ms
Enter
Sleep 400ms
Type "cat assets/demo-transcribe.log"
Sleep 400ms
Enter
Sleep 6500ms

# ---- Beat 4: real cached output proves the pipeline ----
Type "clear"
Enter
Sleep 300ms
Type "head -8 qa-out/v0101-smoke/videos/01*.srt"
Sleep 400ms
Enter
Sleep 4500ms

# ---- Beat 5: the flagship use case — research ----
Type "clear"
Enter
Sleep 300ms
Type "# flagship use case: feed Claude's research with video transcripts"
Sleep 300ms
Enter
Sleep 400ms
Type "neurolearn research --help"
Sleep 400ms
Enter
Sleep 5500ms

# ---- Beat 6: closing pointer to docs ----
Type "clear"
Enter
Sleep 300ms
Type "# docs + 8 use cases:  github.com/nekith78/neurolearn"
Sleep 300ms
Enter
Sleep 2500ms
