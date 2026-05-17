# neurolearn demo tape — deterministic terminal cast for the README.
#
# Run:
#   brew install vhs                              # one-time
#   vhs assets/demo.tape                          # produces assets/demo.gif
#
# Targets ~30 seconds: enough to show the command surface without
# being unwatchable. No network calls — the demo runs against the
# bundled qa-out/v0101-smoke batch so it's reproducible on any
# machine that has the repo checked out.

Output assets/demo.gif

Set FontSize 14
Set Width 1100
Set Height 720
Set Theme "Catppuccin Mocha"
Set Padding 18
Set TypingSpeed 35ms
Set PlaybackSpeed 1.0

# Banner
Type "# neurolearn — transcribe and report on any video"
Sleep 800ms
Enter
Sleep 400ms

# Top-level help
Type "neurolearn --help | head -20"
Enter
Sleep 3s

# Show backends
Type "clear && neurolearn config show 2>&1 | head -12"
Enter
Sleep 3s

# Look at an existing transcribed batch
Type "clear && ls qa-out/v0101-smoke/"
Enter
Sleep 2s

# Show the SRT preview
Type "head -8 qa-out/v0101-smoke/videos/*.srt"
Enter
Sleep 2500ms

# Show the PDF report exists
Type "ls -lh qa-out/v0101-smoke/smoke_v0102_report.pdf"
Enter
Sleep 2s

# Highlight the report subcommand
Type "neurolearn report --help | head -18"
Enter
Sleep 3s

# Closing
Type "# 8 backends · YouTube/IG/TikTok · RSS subscribes · PDF reports"
Sleep 1500ms
Enter
Sleep 1500ms
