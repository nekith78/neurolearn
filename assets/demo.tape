# neurolearn demo tape — README hero GIF.
#
# Regenerate with:
#   brew install vhs      # one-time
#   vhs assets/demo.tape  # produces assets/demo.gif (deterministic)
#
# No network calls. Runs against the bundled qa-out/v0101-smoke
# batch so anyone can reproduce the demo from a fresh checkout.
#
# Design notes:
#   * Pure ASCII in every typed string. Unicode (em-dash, middle dot)
#     gets mangled by some terminals into multi-byte escape sequences
#     that swallow surrounding characters.
#   * Typing speed = 70ms. Faster looks impressive but vhs occasionally
#     drops the leading characters of fast Type commands.
#   * One command per Type, no `&&` chains. Cleaner timing, easier to read.

Output assets/demo.gif

Set FontSize 14
Set Width 1100
Set Height 720
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 70ms
Set PlaybackSpeed 1.0

# Hidden setup. vhs runs commands in a non-interactive shell that
# doesn't load ~/.zshrc, so the project venv binary isn't on PATH.
Hide
Type "export PATH=$PWD/.venv/bin:$PATH"
Enter
Sleep 300ms
Type "clear"
Enter
Sleep 500ms
Show

# 1. Top-level help — see what the CLI offers.
Type "neurolearn --help"
Sleep 500ms
Enter
Sleep 4s

# 2. Show the batch subcommand surface (no secrets in output).
#    Originally `neurolearn config show` lived here, but it prints
#    last 4 chars of the active API key (e.g. "AIza***Odnw") and we
#    don't want a public README GIF leaking key fragments.
Type "clear"
Enter
Sleep 400ms
Type "neurolearn batch --help"
Sleep 500ms
Enter
Sleep 4s

# 3. An already-transcribed batch on disk.
Type "clear"
Enter
Sleep 400ms
Type "ls qa-out/v0101-smoke/"
Sleep 500ms
Enter
Sleep 2500ms

# 4. SRT preview — proves the transcription is real.
Type "head -8 qa-out/v0101-smoke/videos/01*.srt"
Sleep 500ms
Enter
Sleep 3s

# 5. The PDF report file.
Type "ls -lh qa-out/v0101-smoke/smoke_v0102_report.pdf"
Sleep 500ms
Enter
Sleep 2500ms

# 6. Report subcommand help — final beat.
Type "clear"
Enter
Sleep 400ms
Type "neurolearn report --help"
Sleep 500ms
Enter
Sleep 4s
