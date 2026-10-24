# Prompt 2 — Next slice

Use this for slices 2 to 6, in the same agent session, or in a new one if the old one
has lost its context. Replace `<N>` and `<NAME>` with the slice number and name from
`BRIEF.md` §6.

---

Continue the reference engine. Re-read `BRIEF.md` §2 and §5. Then read
`docs/IMPLEMENTATION_NOTES.md` and `docs/AMBIGUITIES.md` to see where the work stands.

Your task now is **slice <N>, <NAME>**, and nothing beyond it.

1. Read the sections `BRIEF.md` §6 lists for this slice, in full.
2. Add a section "Slice <N> — plan" to `docs/IMPLEMENTATION_NOTES.md`, in the same form
   as before:
   - the entities, operations, and rules, with section references;
   - new unclear points, also added to `docs/AMBIGUITIES.md`.
3. Implement the slice. Do not change earlier behavior unless the specification
   requires it. Where it does, say so in the notes.
4. Write tests for every rule in the plan; run the whole test suite, earlier slices
   included, until it passes.
5. Finish with the slice report:
   - what was built;
   - the tests and their result;
   - the new entries in `docs/AMBIGUITIES.md`;
   - anything not implemented, and why.

The constraints of `BRIEF.md` §2 still hold: no conformance tests, no silent decisions,
nothing from later slices.
