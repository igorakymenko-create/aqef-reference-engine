# AQEF Reference Engine — kit

A kit for building a minimal AQEF engine (P2) with an AI coding agent, from the
specification text alone.

| File | Purpose |
|---|---|
| `BRIEF.md` | What to build, the rules, the scope, the stack, where implementations go wrong, the slices and what to read for each. The agent reads it first. |
| `PROMPT-1-START.md` | The prompt that starts slice 1. |
| `PROMPT-2-NEXT-SLICE.md` | The prompt for slices 2 to 6. |
| `PROMPT-3-REVIEW.md` | How failures from the conformance tests go back to the agent: only engine defects, never the test text. |
| `spec/` | AQEF Working Draft 0.41.1, complete, without the Conformance Test Specification. Unmodified copy of the repository at commit `b9ab587`; the specification text is that of release v0.41.1. |

How it is used:

1. Open the kit folder in the agent's IDE, as the workspace, and send
   `PROMPT-1-START.md`.
2. When the agent reports slice 1 done, run the conformance tests of the matching
   sections against the engine.
3. Sort the failures: engine, test, or specification defect.
4. Send only the engine defects with `PROMPT-3-REVIEW.md`.
5. Repeat for slices 2 to 6 with `PROMPT-2-NEXT-SLICE.md`.

Keep `docs/AMBIGUITIES.md` from the agent: it is the main output for the specification,
alongside the test results.
