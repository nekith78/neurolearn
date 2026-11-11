# Bounded parallel execution

Use this for creating/resuming a large study when subagents are available and authorized. Small studies may execute inline; roles below are responsibilities, not a mandatory count of simultaneous agents. Without subagents, preserve the same source records and state checks and report any independent-review limitation.

## Work graph and ownership

| Role | Input and responsibility | Exclusive output |
| --- | --- | --- |
| Coordinator | Scope, authorization, ready/failed work, resource budget, assignments | Shared study state and ownership register |
| Acquisition controller | Invoke NeuroLearn `smart`, verify finished per-video artifacts | Separate attempt directory per video/run |
| Source analyst | Complete transcript and shared analysis contract | One video's primary analysis |
| Independent reviewer | Original evidence, scope, assigned review material | Findings and review coverage; not another worker's analysis |
| Topic synthesizer | Detailed source records and original context after primary corpus analysis | Assigned topic synthesis |
| Visual reviewer | Late transcript-derived candidates grouped by video | One video's observations and retained visual evidence |
| Assembler | Reviewed source/topic records | Shared index and final draft |
| Final verifier | Final claims and original supporting evidence | Final evidence findings/acceptance |
| Cleanup owner | Completed gate and registered temporary-file ledger | Cleanup result and updated ledger |

Different source analyses can run while later transcripts are acquired. A transcript becomes ready only after command completion and validation. Thematic synthesis waits for every selected source's primary analysis or explicit failed/unavailable outcome. Visual review happens late; final synthesis integrates its observations. Final verification precedes cleanup, followed by retained-reference validation.

## Keep contexts bounded and sources accessible

A source worker gets the study goal, current policy/scope, output contract, video identity, exact transcript/version path, and assigned output path. It need not inherit the whole conversation, other videos, or previous analyst conclusions. It reads the full assigned source.

For a very long source, assign explicit contiguous ranges with semantic boundary context, then appoint one owner to reconcile full-video coverage and conditions crossing ranges. Topic workers receive detailed indexed records and can open their original source intervals. Compact coordinator summaries are navigation, not evidence for the final result.

One writer owns each artifact. Workers return structured outputs and bounded reports; they do not rewrite shared indexes, mutate source versions, or create uncontrolled nested agent trees. Only completed, stable versions are consumed; a corrected version invalidates dependent checks and conclusions explicitly.

## Resource and failure control

Coordinate separate limits for network/acquisition, active analysis agents, and heavy ffmpeg/video work. Do not multiply independent worker pools without accounting for their combined operations and built-in retries. Use observed source size, limits, errors, capacity, and machine load; there is no universal worker count or measured speedup supplied by this skill.

Avoid duplicate downloads, giving the same video to multiple acquisition owners, repeatedly loading the corpus into the coordinator, or extracting the same candidates in conflicting directories. Group visual intervals by video and serialize its extraction; independent videos can use isolated directories.

Restart only the affected operation using its saved checkpoint and prior artifacts. A failed item need not block unrelated ready work, but remains visible in coverage. Rate limits, exhausted authorization, or policy conflicts pause the affected work; they do not authorize new providers, local computation, or larger spend.

Record stage time, waiting, errors/retries, completion counts, and review findings during an authorized run. Tune within its approved boundary. No extra paid benchmark is implied by studying a channel.
