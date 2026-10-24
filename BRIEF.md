# AQEF Reference Engine — Implementer's Brief

## 1. What you are building

A minimal working engine that implements the **AQEF specification, Working Draft 0.41.1**,
included in full in `spec/`. AQEF (AI Quality Engineering Framework) specifies how AI
systems are tested. It covers:

- configuration: Projects, Environments, Suites, Scenarios, Quality Contracts, and
  Quality Gates;
- execution against the system under test, with Evidence recorded;
- assessment by Validators and Judges, producing Results;
- a decision path from Results through Quality Gates to a Release Decision;
- governance over who may do what.

The engine's purpose is to show that the specification can be implemented as written.
It is not a product. Where the specification is unclear, contradicts itself, or seems
impossible to implement, that is a finding to record. It is not a problem to work around
quietly.

## 2. Rules that override everything else

1. **The specification is the only authority.** This brief is a reading guide. Where it
   seems to disagree with `spec/`, the specification is right. Record the disagreement
   in `docs/AMBIGUITIES.md`.
2. **Do not look for, ask for, or use the AQEF Conformance Test Specification.** It
   exists and will be run against your engine later, by someone else. The engine must be
   built from the specification text alone, so that passing those tests means something.
   If you find yourself wanting the tests, record what the specification left unclear
   instead.
3. **Never decide an ambiguity silently.** When the text allows more than one reading,
   pick the more conservative one and record it in `docs/AMBIGUITIES.md`. The more
   conservative reading is the one that rejects more, blocks more, or records more.
   Each entry gives the section, a quotation, the readings you saw, and which one you
   chose and why.
4. **Normative language.** MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY have the meanings
   of `spec/front-matter/09-normative-language.md`.
   - Implement every MUST and MUST NOT that applies to the capabilities in §3.
   - Implement SHOULDs where reasonable; list any you skip in
     `docs/IMPLEMENTATION_NOTES.md`, with the reason.
5. **Do not weaken a rule to make something work.** If a rule blocks you, stop and record
   it.
6. **No features beyond the specification.** Nothing extra, no shortcuts that bypass a
   governed action, and no "admin override" that the specification does not define.

## 3. Scope

The Conformance Statement this engine will eventually publish (§10 of the
specification) claims:

| Capability | Meaning |
|---|---|
| core | the non-negotiable core: everything not tied to a scoped capability |
| `human_review` | Human Reviewer as an Oracle; Human Review |
| `multi_judge` | Multi Judge, Consensus, Voting |
| `seeded_controls` | Seeded Controls, clean controls, invalidation, requalification |

Not in scope:

- `action_boundary`: acting subjects with tools; reject a configuration that needs it;
- Dataset sources other than Static;
- plugins, SDKs, CLI, Reference UI, CI/CD integrations, and named test types.

Read §10 (`spec/front-matter/10-conformance.md`) first. It defines exactly what a claim
covers.

## 4. Technology

- **Stack.** Python 3.12, FastAPI, SQLite, pytest. Keep dependencies few and pinned.
- **API.** The REST API of Appendix C is the engine's interface. Everything an external
  tester needs must be reachable through it.
- **Authentication.** Every request is made by a Principal, a Person or a Service
  Account (Volume XII, Principals; Appendix C §C.4). A bearer token per Principal is
  enough. Document how Principals, Teams, Roles, and Permissions are created.
- **Model calls.** The system under test, and every Judge, is reached through a provider
  interface.
  - Ship one HTTP provider. It maps a model identifier (an Environment's
    `model_version`, a Judge's `model`) to a URL configured in the engine's own settings,
    not in the AQEF configuration.
  - The subject receives the rendered Prompt and returns a Response.
  - A Judge receives the Evidence and its criteria and returns a verdict and a
    Confidence.
  - Document the exact request and response JSON in `docs/PROVIDERS.md`. An external
    test harness will play the subject and the Judges through this interface, so it must
    be complete and stable.
- **Errors.** Rejections must be observable: an HTTP error status and a body naming
  the reason. The specification does not fix status codes; choose consistent ones and
  document them.

## 5. Places where implementations usually go wrong

These are pointers, not rules. The rule is always in the section named. Read it there.

1. **Recorded Results are never modified** (Volume I, Chapter 6, Result Resolution;
   Appendix C §C.7; Appendix B §B.3).
   - What changes is the *effective* state, which is derived: resolution by a later
     Result (`resolves`), invalidation by a Seeded Control (`invalidated_by`), and
     staleness against a Snapshot.
   - Store records append-only and compute effective state; never overwrite.
2. **Confidence is never bare `null`.** It is a number or `"not_applicable"`, and a
   Validator has none (Appendix C §C.7). Disposition has a closed set of values.
3. **Validation before Evaluation** (Volume I, Chapter 3; Volume V), with
   short-circuiting. A Retry never replaces a Response that was received (Volume III,
   Retry). An Oracle call may be re-attempted only before any verdict was returned
   (Appendix C §C.7).
4. **Contract composition is additive** (Volume VII; Appendix A).
   - A lower level adds clauses and cannot remove or weaken a higher level's.
   - Two clauses are the same clause only when they share an `id`.
   - A conflict is surfaced, never silently resolved.
5. **Quality Gates** (Volume I, Chapter 6, Aggregate Basis and Quality Gates; Appendix A
   §A.10, §A.12; Appendix B §B.3).
   - A Gate that includes any effective Result that is not `actionable` fails, and no
     configuration turns that off.
   - A failed GateResult lists every reason that applies.
   - Every aggregate states its basis. Seeded Control Results are never aggregated.
6. **Release Decisions** (Volume I, Chapter 6; Appendix A §A.13, §A.14; Appendix C §C.3).
   - A Release Decision references a Snapshot, and is rejected if the configuration in
     its scope changed since.
   - An override binds to exactly one GateResult.
   - Who may take which governed action, Person or Service Account, is in Volume XII,
     Principals.
7. **Seeded Controls** (Volume VIII, Seeded Controls; Appendix A §A.1, §A.4, §A.9;
   Appendix C §C.3).
   - Outcomes are confirmed or `invalid`.
   - Invalidation is derived and recorded once, in `seeded_control_results`.
   - A false alarm on a clean control counts as a miss in every rule.
   - Requalification and `reassess` have separate conditions.
8. **Admission** (Volume VI, Admission; Appendix C §C.3).
   - The engine sets `id`, `recorded_at`, and `recorded_by`.
   - The most recent accepted record decides admission.
   - The record has consistency rules that MUST reject a bad request.
9. **Every Report signal is an always-present list** (Appendix C §C.10; Volume XI).
10. **Deletion keeps history** (Appendix C §C.8).

## 6. Slices

Build in this order. Each slice must run, and its own unit tests must pass, before the
next one starts. After each slice, the project owner may send back a review of failures
found by external testing. Fix those before going on.

| Slice | Content | Read first |
|---|---|---|
| 1. Foundation and Definition | Principals, Teams, Roles, Permissions, authentication, audit log; Projects, Environments, Suites, Scenarios, static Datasets with versions, Quality Contracts with composition, Quality Gates; loading and validating configuration; governed changes through the Approval Workflow | §8, §9, §10; Volume II; Volume VII; Volume XII (Teams to Approval Workflow); Volume IV (Static, Versioning); Appendix A; Appendix B; Appendix C §C.1–§C.6, §C.8 |
| 2. Execution and Evidence | Executions and batches, the Execution Pipeline, Runtime, Scheduling, Retry, Timeouts, Variables, Context, Conversations, Artifacts; the provider interface for the subject | Volume III, all but Action Boundary; Volume I, Chapter 4; Appendix C, executions and their sub-resources |
| 3. Assessment | Validators (built-in and Custom); Single Judge; Confidence; the Result shape; Admission | Volume V; Volume VI (Judge Architecture, Single Judge, Confidence, Admission); Volume I, Chapter 3; Appendix C §C.7 |
| 4. Decision and Release | Result Resolution (`review`, `reassess`); aggregation; Aggregate Basis; Quality Gates and GateResults; overrides; Snapshots; staleness; Baselines; Release Decisions and Release Policies; Reports | Volume I, Chapter 6; Volume X; Volume XI; Appendix A §A.10–§A.14; Appendix C §C.3 (gates, overrides, snapshots, baselines, releases, release policies, reports), §C.10 |
| 5. Scoped capabilities | Human Review, Multi Judge (Consensus, Voting, quorum), Seeded Controls (defect and clean, confirmation, invalidation, `halt_run`, requalification) | Volume VI (Multi Judge to Human Review); Volume VIII, Seeded Controls; Appendix A §A.1, §A.4, §A.7, §A.9; Appendix C §C.3, seeded controls and requalifications |
| 6. Conformance Statement | Publish the statement of §10, and review the whole engine against it | §10; `docs/` |

Appendices D (Glossary), E to G (diagrams), H (examples), and I to K (guides) are
reference. Use the Glossary for terms. Examples in Appendix H are illustrative: where an
example and a normative table disagree, follow the table and record the disagreement.

## 7. Repository and deliverables

```
aqef-engine/
  engine/            the package
  tests/             your own unit and API tests
  docs/
    IMPLEMENTATION_NOTES.md   per slice: what was built, SHOULDs skipped and why
    AMBIGUITIES.md            every unclear point: section, quotation, readings, choice
    PROVIDERS.md              the provider interface, exactly
    API.md                    how to run the engine; status codes; how to create Principals
    CONFORMANCE-STATEMENT.md  slice 6
  README.md
```

- Do not write a test harness for the Conformance Test Specification. That is a separate
  project.
- Do not add a license file. The project owner will choose the license.
- Each slice ends with a short report: what was built, what tests you wrote, and the new
  entries in `AMBIGUITIES.md`.
