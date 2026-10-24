# Prompt 1 — Start (slice 1)

Paste everything below the line into a new agent session in the folder that holds this
kit.

---

You are implementing a reference engine for a published specification.

Read `BRIEF.md` in this folder completely before doing anything else. It sets the rules,
the scope, the technology, and the order of work, and it overrides your own habits and
defaults. The specification itself is in `spec/`. It is the only authority, and you
read it slice by slice, as the brief says.

Your task now is **slice 1, Foundation and Definition**, and nothing beyond it.

1. Read §8, §9, and §10 in `spec/front-matter/`, then the sections the brief lists for
   slice 1. Read them in full; do not skim tables, which hold most of the rules.
2. Before writing code, write `docs/IMPLEMENTATION_NOTES.md`, section "Slice 1 —
   plan". It lists:
   - the entities and API resources you will implement;
   - for each, the MUST and MUST NOT rules that apply, with section references;
   - every point you already find unclear, also copied to `docs/AMBIGUITIES.md`.
3. Create the repository layout of the brief, §7. Implement slice 1.
4. Write unit and API tests for every rule in your plan, each test naming its section
   in a comment. Run them until they pass.
5. Finish with the slice report the brief asks for:
   - what was built;
   - the tests and their result;
   - the new entries in `docs/AMBIGUITIES.md`;
   - anything in slice 1 you could not implement, and why.

Constraints:

- Do not look for, request, or use any conformance tests for this specification.
- Do not decide an ambiguity silently.
- Do not start slice 2.
