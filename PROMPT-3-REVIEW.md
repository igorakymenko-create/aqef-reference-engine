# Prompt 3 — Review of external test failures

The project owner runs the conformance tests against the engine after each slice. A
reviewer first sorts every failure into one of three kinds:

- **engine defect:** the engine does not do what the specification says;
- **test defect:** the test is wrong, and the test is fixed;
- **specification defect:** the text is wrong or unclear, and the specification is
  fixed.

Only engine defects go to the agent, in the form below. Never paste the test text: give
what was observed, what the specification requires, and where. This keeps the engine
built from the specification, not from the tests.

---

External testing found the defects below in the engine. Each gives what the engine did,
what the specification requires, and the section that says so.

For each defect:

1. Read the section named. If you believe the specification does not require what the
   review says, do not change the code. Reply with your reading and a quotation, and
   add an entry to `docs/AMBIGUITIES.md`.
2. Otherwise fix it, and add a test that would have caught it, naming the section.
3. Run the whole test suite until it passes.

Finish with a list:

- each defect with its outcome: fixed, or disputed with the reason;
- any other code the fixes changed.

Defects:

<!-- One block per defect:
### D-<n>
- Observed: <what the engine did, concretely: the request and the response or state>
- Required: <what the specification requires>
- Section: <Volume or Appendix and section>, "<quotation>"
-->
