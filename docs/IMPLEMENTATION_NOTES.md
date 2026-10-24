# Implementation Notes

## Slice 6.1 — D-7

- Confirmed Appendix B B.3 Governed configuration change: presence of a Contract is
  not a change. Compare normalized governed values by attachment path after Pydantic
  defaults/dimensions/enums resolve, under the configuration lock. Variable/prompt-only
  edits and echoed Contracts need only the operation's edit Permission; no new Approval.
- Compare all nested project/suite/scenario contracts and Gates on Project PUT, including
  removals. Creation paths still govern newly attached definitions. Dedicated Contract/
  Gate endpoints retain their own C.3 contract_define operation Permission.
- Tests cover Person/Service unchanged-normalized/Variable edits, every nested attachment
  level and added/removed/different values, denied changes leaving configuration intact.
- Whole suite: **349 passed**, one existing Starlette/httpx deprecation warning. No new
  ambiguous reading: B.3 explicitly says creating or changing. D-6 is its separate commit.

## Slice 6.1 — D-6

- Confirmed XII Principals/Audit and C.8 require comprehensive action provenance.
  Added request-local auditing of successful permission checks and existing semantic
  events, Principal id/kind on Executions, and explicit deletion intent. Retained-history
  URLs and global/read-action audit semantics are documented in API and ambiguity 34.
- Regression tests name XII/C.8 and cover Person/Service triggers, denied preflight,
  retained deletion and historical reads, global/read actions, Human Review, control
  confirmation/invalidation and Scenario deletion. Prior audit tests select their
  governed action rather than assuming that no other actions are recorded.
- Whole suite: **323 passed**, one existing Starlette/httpx deprecation warning.

## Slice 6 — Completed Work

- Published CONFORMANCE-REVIEW.md: 402 normative source units (paragraphs, mandatory
  table rows and B.2 property blocks), evidence catalogue with real module/test names,
  per-Volume/Appendix scope accounting, and explicit partial/untested findings. Related
  happy-path coverage is never represented as a full property rejection proof.
- Published CONFORMANCE-STATEMENT.md using §10's specification version and identifiers:
  human_review, multi_judge, seeded_controls; core implicit. It documents unoffered
  capabilities and implementation-defined choices and withholds an unqualified claim
  of Conformance because G1, G3–G8 and U1 remain open. G2 is closed by the correction below.
- Small normative corrections: authenticated framework docs/OpenAPI/health (C.4);
  required Row.variables (A.8/B.2); resolved Service Account owner to an existing Person
  at load/storage (XII/C.4); applied existing offset/limit pagination to ten older
  collection routes (C.6). No new capability or background execution feature was added.
- API/PROVIDERS/README now describe actual synchronous behavior, accepted fixed
  Conversation, nullable/default fields, current authentication/bootstrap behavior,
  pagination, errors, cancelled work and separate assessment timeouts. OPENAPI.json is
  generated from 71 registered operations; unconstrained dynamic response schemas are
  disclosed as G3 rather than portrayed as complete runtime types.
- New ambiguity entries **30–33**: qualified scope declaration, asynchronous REST,
  inherited policies and timeout boundary. Older choices are cross-referenced/superseded
  where the review exposed a gap. No external/conformance test material was accessed.
- Whole suite: **318 passed**, one Starlette/httpx deprecation warning; 19 new slice 6
  regression cases. D-5 separately passed 299 and was pushed as 5b0ade0 / slice-5.1.
- Deliberate SHOULD deviations (with full sources/reasons in the statement): external
  family/provenance and blind reference labelling cannot be verified by this adapter;
  no automatic Requirements/Risk feedback or semantic assertion decomposition; no
  generated/rotating/blinded control-authoring workflow or mandatory recent source
  Evidence; late human confirmation permitted; recommended date/Team/Baseline filters
  not implemented; generated OpenAPI is not a complete prose-derived JSON Schema.
  These decisions do not excuse separate MUST gaps G1/G3–G8/U1. Cheapest-first checks,
  pure validator inputs, controls-first/fail-fast and zero-prior confirmation are followed.

## Slice 6 — plan

- Review §9/§10, the seven principles and all mandatory normative units in scoped
  Volumes I–VIII, X–XII, XVII and Appendices A–C (including property blocks required
  by B.2). Reference Appendices D–K and unoffered capabilities receive an explicit
  scope disposition, not a fictitious implementation/test citation.
- Publish a source-linked MUST/MUST NOT ledger in CONFORMANCE-REVIEW.md. Distinguish
  traced implementation/tests from partial, untested and missing behavior; retain
  known gaps instead of representing passing unit tests as proof of Conformance.
- Publish §10's specification version and capability identifiers; the non-negotiable
  core is implicit, never a capability identifier. State unoffered capabilities,
  implementation-defined choices, deliberate SHOULD deviations and unresolved gaps.
- Compare API/PROVIDERS/README with actual registered operations and model schemas.
  Correct documentation; code changes only for small, unambiguous normative defects.
- No new features, no external/conformance test material. D-5 precedes this slice as
  its own commit/tag. New interpretations and scope findings will be recorded below
  and in AMBIGUITIES.md with source quotations.

## Slice 5.1 — D-5 external review

- A.4 FixedEvidence requires the stored Conversation form. Replaced the unconstrained
  conversation field with the shared runtime Conversation model (nonempty turns,
  strict string prompt/response, forbidden extra fields). Every configuration loader
  now rejects unreadable Evidence before storing it, with the normal 422 field path.
- Regression test `test_a4_fixed_evidence_conversation_rejected_at_every_configuration_load`
  exercises Project POST/PUT, Suite POST and Scenario POST/PUT with message arrays,
  empty turns and nonstring responses, and confirms rejected replacements leave
  configuration unchanged. Existing construction tests cover accepted execution form.
- API documents the accepted JSON form. No new ambiguity: A.4 is explicit.
- Whole suite: **299 passed**, one existing Starlette/httpx deprecation warning.
  Two earlier tests were updated to supply valid Conversation fixtures and expect
  invalid shape rejection at load rather than after direct storage corruption.

## Slice 5 — Completed Work

- Built Human Review pending/completion and Role/timeout routing; independence/stability
  panels, voting/weighted consensus, quorum, member evidence and panel Admission;
  persistent defect/clean controls, actual-Evidence confirmation, class/Oracle-scoped
  invalidation, halt_run, explicit full-run invalidation and fresh-control Requalification.
- Reassessment uses frozen Evidence, retains earlier verdicts and requires a qualified
  corrected Oracle after control failure. Reports expose control/panel signals and
  derived invalidation; late confirmation also invalidates cached evaluation freshness.
- Required earlier-slice changes: guarded Result resolution after invalidation; recursive
  panel Admission; controls scheduled before ordinary work and excluded from Basis;
  provider member calls; optional execution Gate selection; ISO review durations;
  explicit per-control prior provenance. Existing recorded Results remain immutable
  except the specified completion of awaiting_review Human Results.
- API examples cover review, completion, confirmation, full-run invalidation,
  Requalification/reassess and control/panel response locations. PROVIDERS documents
  individual member URLs and unchanged exact Judge wire messages.
- Validation: **284 passed**, including all previous slices and 47 new scoped tests.
  One existing Starlette/httpx deprecation warning. D-4 was separately committed and
  pushed as f1a2f01 / slice-4.1; its C.10 denominator regression remains included.
- New ambiguity entries **25–29** document every implementation choice listed below.
- Limits: generator selection/blinding and authorship/reference-model provenance are
  supplied by configuration and external reviewers; the engine cannot verify hidden
  training data or model ancestry. No generator/UI or conformance statement was added.
  Single-Judge low-confidence automatic routing is optional and remains explicit review.
  Execution retains the earlier synchronous single-process interface. No slice 6 work
  or external/conformance test material was used.

## Slice 5 — plan

### Entities and operations
- Human Reviewer Oracle and pending review routing/completion, block/escalate timeout
  state; existing C.3 review endpoint plus read-only routing information (VI Human Review;
  A.5; C.7). Timed-out reviews stay blocking and never invent a verdict.
- Multi Judge independence/stability, voting/confidence_weighted_mean, quorum, panel
  metadata and per-member evidence (VI Multi Judge/Consensus/Voting/Confidence; A.7).
- Batch-scoped Seeded Control records, confirmation by construction/Validator/Person,
  derived invalidation, skip_class/halt_run, explicit full-run invalidation, fresh-control
  Requalification and guarded reassessment (VIII Seeded Controls; C.3; A.1/A.4/A.9).

### Rules and references
1. Direct Human Expectations produce awaiting_review with null verdict and inapplicable
   Confidence. Low Confidence/unresolved panel consensus may route to a separate Human
   Result resolving the original. Person+review and the routed Role are required;
   captures_confidence determines whether numeric Confidence is required. Completion
   preserves id/recorded_at; escalation changes routing, never verdict (VI; A.5; C.3/C.7).
2. Independence calls each configured Judge once at its own startup-mapped URL; stability
   calls one configuration samples times. Every member sees the same frozen Evidence
   and literal criteria. Preserve per-member verdict/Confidence/error with stable IDs.
   Panel Result includes configured/counted; panel identity includes purpose/configuration.
   Missing availability is never a pass (VI Multi Judge; C.7).
3. Voting counts qualified members/samples: majority > half, unanimous all, numeric
   threshold ceil(fraction*count), default human_review on no winner. confidence_weighted_mean
   is explicit and min_agreement applies. Confidence remains the members' own uncertainty;
   agreement is separate supporting evidence, never substituted for Confidence. Quorum
   defaults full configured count; below it yields not_assessed. A miss excludes all
   stability samples of that Oracle (VI Consensus/Voting/Confidence; A.7).
4. Controls run before ordinary assessments, preserving deterministic order and private
   state. Confirm actual Evidence before any catch/miss claim. Unconfirmed/failed-confirmation
   controls are invalid, infer nothing about any Oracle. Clean controls confirm absence;
   defect controls confirm presence. Fixed Evidence never calls subject. Human confirmation
   can update derived outcome later without rewriting Results/GateResults/Releases (VIII).
5. Each run has one persisted control entry per Scenario, with per-Oracle details when
   there are several. A defect catches only fail; clean passes only pass, with usable
   Confidence. Miss/false_alarm affects same Oracle and declared defect classes; undeclared
   clauses cover every class. Results stay unchanged; invalidated_by is derived. Later
   affected assessments record not_assessed without Oracle calls, others continue (VIII;
   C.3/C.7). Control Results never enter aggregates or Basis.
6. halt_run stops subsequent subject/Oracle work and records full_run, reason halt_run.
   Existing Results of all classes/Oracles are blocked; explicit invalidate requires
   seeded_control_invalidate, a real miss and a nonempty logged reason. Gate reasons
   distinguish defect miss/clean false alarm; Report/evaluation freshness includes derived
   invalidation, so a late confirmation cannot leave a misleading latest Gate (VIII; C.3).
7. Requalification records exact Oracle/class and fresh successful control Result IDs;
   reject wrong class/Oracle/outcome and any control exposed by a miss/false alarm in a
   run to be reassessed. Reassess needs a different corrected Oracle and qualification
   for every applicable class, of every failed kind (defect/clean/both). Same Oracle only
   recovers oracle_unavailable, never a genuine verdict; no subject call. Original chain
   stays intact; current effective state alone determines resolvability (VIII; I Ch.6; C.3).
8. Class/control difficulty defaults not_established, never zero; numeric priors require
   basis/source and independent reference Oracle provenance. Never update from tested
   Oracle performance. No-reference-catch controls require Human confirmation before
   gating. Exposure/generator/source_execution SHOULDs and unverifiable provenance are
   explicitly documented rather than invented (VIII; A.1/A.4).
9. Report keeps all C.10 lists, complete low_confidence denominators (D-4), panel purpose
   and every unadmitted member configuration; a panel is admitted only if every member
   configuration is admitted. Derived invalidation blocks Gates and remains visible in
   metadata/results. Auth/permissions, immutable history, pagination and prior suites
   continue to hold (VI Admission; C.3/C.7/C.10).

### Unclear points
Entries 25–29 record panel Confidence/availability, routing defaults/timeouts, per-Oracle
control outcomes, requalification binding/freshness and prior provenance. No slice 6 work.

## Slice 4.1 — D-4 external review
- Confirmed Appendix C C.10 explicitly requires per-Scenario/per-Oracle inconclusive
  and total counts. Removed the filter that hid pairs with zero inconclusive Results.
- Regression test names C.10 and I Ch.6 Aggregate Basis: three Scenarios, one Judge,
  two inconclusive and one actionable, preserving all three denominator entries.
- Report remains frozen; no recorded Result is modified. Correction committed/tagged
  separately before slice 5. Whole suite: **237 passed**; one existing Starlette/httpx deprecation warning.

## Slice 4 — plan

### Entities and operations
- Effective Result chains: review/reassess endpoints under Execution Results, append-only
  resolutions and the one awaiting_review completion exception (I Ch.6 Result Resolution;
  C.3, C.7). Reassessment uses stored Evidence and the frozen clause/Oracle only.
- Decision service: Metrics, Confidence-modeled weighted aggregates and Basis; batch
  Gates/check producing immutable GateResults and an automatic scoped Snapshot (I Ch.6;
  X; A.10–A.13). Baselines and explicit Snapshots have list/get/create APIs.
- Report: explicit POST generation for one batch plus list/get, frozen C.10 shape and
  six always-present signal lists (XI Reports; C.10).
- Governance: per-GateResult override, Person-approved Baseline, Release Policies and
  revocation, Release Decisions tied to a Report and current Snapshot (XII; A.11–A.14).

### Rules with section references
1. Resolutions are linear: only current non-actionable effective Result; actionable
   cannot reopen. Human review is Person+review (and clause role where declared), only
   inconclusive/unresolved Human Results; same-Oracle reassessment only unavailable.
   Both preserve old records; no subject call; no requalified-control behavior before
   slice 5. Unique resolution links prevent competing branches (I Ch.6; C.3/C.7).
2. Apply Confidence before aggregation: use effective actionable Results at face value;
   non-actionable/stale/unadmitted Results block and are counted separately. Positive
   Contract weight affects pass rate; deterministic Safety failure is an independent
   veto, never outvoted. Seeded Controls are excluded from every aggregate/basis (I Ch.6).
3. Every Gate reads all relevant dimension Results, reports distinct Scenario/Execution
   counts and min_basis_met/not_declared; all applicable failure reasons are retained.
   Empty evidence is not_computed and cannot pass. All Project and scoped Suite Gates
   are evaluated, advisory and blocking; unknown metrics/threshold syntax rejected
   rather than guessed (I Ch.6; A.10/A.12; C.3).
4. Snapshot freezes Environment, inline Contracts in attachment order, every referenced
   reusable Contract with content-hash version, Gates and scoped Baselines. Staleness
   compares full Environment and identified clause content, unnamed clauses against
   whole effective Contract. Re-evaluation never refreshes old Evidence. Release rejects
   any scoped Contract/Gate/Environment change; unrelated scope changes do not affect it
   (I Ch.6 Staleness; X Snapshot Comparison; A.13).
5. Baseline explicitly designates one effective actionable Result/Execution, pins exact
   Evidence, Dataset/version, effective Contract, Oracle, approving Person/role/time.
   Regression compares pass->fail for matching Scenario/clause/Oracle against a named
   Baseline, latest_approved or Snapshot's Baselines; missing comparison cannot pass.
   Drift diagnostics compare prompt/model/dataset/Oracle without literal response diff
   (X; A.11). No automatic baseline replacement.
6. Override names one failed blocking GateResult id AND its batch and Gate, with nonempty
   justification. Person gate_override plus Gate-specific permission; logged Approval
   and Audit; no later evaluation inherits it. Report copies latest GateResults and
   overlays recorded override at generation only (I Ch.6; XII; A.12; C.3/C.5).
7. Report stores C.10 scope, Metrics with definitions and exact Result IDs, all Gates,
   Basis, and six list signals. Frozen after generation, survives live deletion; fresh
   Reports read current Results/Admission and latest evaluations (XI; C.10/C.8).
8. Release requires applicable Gates, matching batch/report/snapshot, current scoped
   configuration. approved iff all blocking Gates pass; overridden iff every failed
   blocking Gate has its own override; rejected remains allowed. Every applicable
   advisory Gate is included. Actor/role/time and Approval/Audit are recorded (A.12).
9. Only Person release_decide may create/revoke a Policy; immutable except revocation.
   Service Account Release requires in-force Policy covering actor/Suite/Environment,
   only approved with all blocking Gates passing without overrides, or rejected.
   Baseline/override are Person-only regardless of permissions (XII; A.14; C.4/C.5).
10. Authenticated reads require read; writes use canonical atomic permissions; bounded
    pagination, typed requests, reason-bearing errors and durable append-only history
    across restart. No slice-5 panels/controls/requalification implemented (C.3–C.8).

### Unclear points
Entries 20–24 record batch scope, thresholds/weights, Report generation, baseline
identity/comparison and review/release authoring fields. Tests cover each numbered rule.

## Slice 4 — Completed Work

### What was built
- `engine/decision.py` and `engine/api/decision.py`: complete batch decision path with
  Confidence-modeled weighted aggregation, separate deterministic Safety/declared veto,
  Basis (including per-metric bases for ThresholdMaps), GateResults and scoped Snapshots.
- Linear review/reassess Result chains with unique resolution links and no subject
  re-invocation; awaiting_review completion is the only in-place Result change and
  preserves recorded_at. Same-Oracle recovery of unavailable Validator/Judge is supported.
- Frozen Reports with exact Result IDs/Metric definitions, all six list signals, explicit
  generation API, and baseline comparison/drift correlations. Reports refresh evaluations
  for changed config, effective Result standing or Admission, and otherwise preserve
  exact GateResult/override identities. Historical Reports never change.
- Person-approved explicit Baselines pin Result, Evidence, Dataset and full configuration;
  regression checks named/latest Baseline or a Snapshot's frozen Baseline IDs.
- Exact-GateResult overrides, standing Release Policy approval/revocation, and Release
  records derived from matching current Snapshot/Report/latest evaluation. Advisory Gates
  are retained. Automation can record only covered approved/rejected decisions under
  an in-force Person-approved Policy; override/baseline/review remain Person-only.
- Persistent append-only decision records, pagination/get APIs and Approval/Audit traces.
  Decision/configuration writes and Admission changes are serialized by a per-Storage
  lock in the single-process Minimal Engine deployment. SQLite unique links independently
  reject duplicate resolution branches.

### Required earlier behavior changes
- Result adds optional resolves; absent remains absent on earlier normal Result shapes.
  Assessment helpers accept a resolution target and re-use frozen Evidence/configuration.
- Empty Dataset batches now persist batch scope alongside executions, allowing Gates
  to record not_computed/insufficient_basis instead of losing the returned batch ID.
- Project GET now reflects current project Gate definitions. Gate list/get/update also
  handle Suite Gates, retaining scope, and registration enforces cross-Suite/Project
  Gate name uniqueness. Full Project round trips cannot revert accepted Gate edits.
- Shared StorageConflictError handling returns an observable 409; old request/error
  conventions and the subject/Judge provider protocols are unchanged.

### Tests and results
- `python -m pytest -q`: **236 passed**, including all 193 cases after O-2 and **43 new
  slice-4 cases** in `tests/test_decision.py`. One existing Starlette/httpx deprecation
  warning remains. `git diff --check` passes.
- Cases cover planned rules 1–10: linear/duplicate/actionable resolution rejection,
  exact Oracle recovery without subject calls, awaiting_review completion/freshness,
  Confidence and admission blocking, weights/maps/resource metrics, Safety/declared
  veto, all applicable reasons, honest Basis and row breadth, seeded-result exclusion,
  empty/failed batches, immutable snapshots/reports, named/unnamed clause staleness,
  unchanged unrelated scope, Project/Suite Gate updates, exact override scope, advisory
  versus blocking/no Gates, Person-only actions and Gate-specific permissions, policy
  actor/Suite/Environment coverage and revocation, approved/rejected/overridden releases,
  explicit Baseline/Snapshot regression, six Report signals, restart and deletion retention.
- New ambiguity entries: **20–24**. O-2 was completed separately in **df49a83**, tagged
  and pushed as slice-3.2 before implementation of this slice. No conformance/external
  test material accessed; no changes to the supplied specification.

### Deliberate limits / deferred work
- Full Human Review routing/escalation/timeouts, Multi Judge panels and seeded-control
  confirmation/invalidation/requalification remain slice 5. This slice implements only
  the resolution endpoints Chapter 6/C.3 require, rejecting requests needing unavailable
  requalification. Their Report signal lists remain present even when empty.
- Action Boundary enforcement/acting tools, nonstatic datasets, UI/Dashboards, SDKs and
  CI integrations remain outside this engine's scope. Existing recorded boundary facts
  can be surfaced without enabling those capabilities.
- Snapshot reusable versions are content hashes because configuration has no explicit
  Contract version field. Full copied contents preserve reproducibility. Aggregate
  statistical intervals are MAY and are not implemented; no statistical number is
  mislabeled Confidence. No in-scope MUST is intentionally omitted.

## Slice 3.2 — O-2 owner decision
- Parameterless Custom Validator Constraints accept expected null or {}. All other
  structures fail model validation at configuration load, naming the clause id (or
  validator/target for an unnamed clause). The shared Constraint model covers Project,
  Suite, Scenario and reusable Contract routes. Defensive runtime checks accept both.
- AMBIGUITIES entry 19 replaces the earlier choice; API.md documents both forms.
- Whole suite: **193 passed**. Seven owner-decision cases replace the previous runtime
  rejection test; the earlier dimension-only test now uses a valid parameterless form.
- This correction is committed/tagged separately as slice-3.2 before slice 4 work.

## Slice 3.1 — External review corrections

### D-3 — accepted configuration replacement takes effect (fixed)
- Read Appendix C §C.3 (Project/Environment/Suite/Scenario/Contract operations) and
  Volume I Chapter 6 (configuration consistency and staleness). The review is required
  by “Replace Project configuration”: acknowledging a new tree while executing the old
  child records was a storage defect, not an alternative interpretation.
- Project PUT now replaces its live Environment/Suite/Scenario records in the same
  SQLite transaction as the parent JSON and updates declared named Contracts/Gates.
  Dataset versions are inserted or reused unchanged; changing a version is a 409 and
  rolls back the entire configuration transaction. Previously registered dataset
  versions and reusable Contracts remain addressable in their independent registries;
  removing a declaration does not silently delete such versioned/reference resources.
- Project GET/list now project current Environment/Suite child records and current
  named project Contract definitions. Individual Scenario/Environment/Contract edits,
  new Suites and Scenario additions/deletions therefore survive a GET/PUT round trip.
  Suites have creation/read routes in C.3, no Suite PUT route was added.
- Configuration changes affect later Executions; frozen earlier Executions/Results are
  retained exactly. No staleness/Gate implementation from slice 4 was added.
- Related code touched: Project and Suite governance now detects nested Scenario
  Contracts; removal of an existing Scenario Contract also requires contract_define.
  This preserves C.5 governance when accepted nested changes become executable.
  Project PUT reports storage conflicts as 409 and checks missing Project as 404.

### O-1 — schema instance is the held target value (owner decision implemented)
- JSON Schema objects/Booleans now validate the target as held in Evidence. A Response
  stays a string; plain nonempty text passes a nonempty string schema, empty text fails.
- JSON syntax checking remains explicit via expected: "json". Dotted paths into a text
  Response still decode JSON during target selection before checking the selected value.
- Updated AMBIGUITIES entry 12 and added entry 18, explicitly marking the previous
  implicit-decoding choice superseded by the project owner's decision. API.md describes
  the resulting behavior. Custom schema rules share the corrected implementation.

### Validation
- `python -m pytest -q`: **187 passed** (168 existing + 19 new regression cases).
- `tests/test_review_slice_3_1.py` names C.3 / I Chapter 6 for D-3 and Volume V Built-in
  Validators for O-1; covers full replacement, sub-resource edits, Suite/Scenario
  additions/removal, named/referenced Contracts, Environment replacement, new Dataset
  version resolution, atomic rollback, retained history, nested governance, plain-text
  and empty Responses, JSON syntax, JSON paths and Boolean schemas.
- Three earlier pure schema test inputs now use actual object values rather than
  JSON-encoded text, retaining their object-schema intent under O-1.
- `git diff --check` passes. The existing Starlette/httpx deprecation warning remains.

## Slice 3 — plan

### Entities and operations
- Validator Engine: built-in schema, structural, forbidden-content, latency and cost
  checks; deterministic project-scoped Custom Validators; target evidence selection.
  Tool-call and boundary checks apply only to the excluded action_boundary capability
  (Volume V Architecture, Built-ins, Custom Validators, SDK; A.5).
- Judge Engine: one HTTP Single Judge per Expectation, explicit criteria and source of
  Confidence, assertions disclosure and unavailable outcomes (VI Architecture, Single
  Judge, Confidence; C.7). Uses the existing startup provider URL mapping.
- Result: append-only C.7 records, automatic after successful Execution only; paginated,
  filterable execution Results resource. Recorded Evidence/configuration remain frozen.
- Admission: Person-only POST and read/list API, strict C.3 consistency validation,
  generated recording fields, append-only acceptance order and latest-status lookup.

### Rules and references
1. Completed Evidence alone enters assessment; all Constraints are checked before any
   Judge. Run cheap built-ins before expensive schema/structural/custom checks, preserving
   declaration order for ties. Record every applied clause's Result, including errors;
   failed/unavailable validation short-circuits Judges as dictated by composition (V
   Execution Order, Composition, Pipeline; I Chapter 3). No placeholder Judge Results
   are fabricated for short-circuited Expectations (C.7 closed dispositions).
2. Validators depend only on selected frozen Evidence and versioned configuration,
   never live time/network/randomness. Verdicts have confidence `not_applicable` and
   sufficient supporting evidence. Missing target/configuration or crashed checks are
   oracle_unavailable, not fail; completed mismatches are fail (V Architecture, SDK).
   AND requires all; OR requires one; veto failure always blocks, and unavailable
   validation blocks even if another OR operand passes (V Composition; C.7).
3. Built-in targets/expected formats are explicitly documented; schema uses local-only
   JSON Schema, forbidden-content literal/regex patterns, structural ordered required
   steps, latency recorded execution duration and cost recorded usage/resources (V
   Built-ins, A.5). Never fetch remote schemas. Unsupported shapes yield unavailable.
4. Custom registration exposes only a restricted declarative deterministic check,
   bound to a Project and immutable name/version/configuration. No arbitrary Python,
   model or HTTP check runs as a Validator. Registration requires contract_define and
   its existing Approval Workflow; public API and examples in API.md. Version/config
   are frozen at preflight (V Custom Validators, SDK; C.4; ambiguity 14).
5. Single Judge receives frozen Conversation/Artifacts and literal criteria; no Judge
   runs as its own subject. Stable Oracle identity covers model, confidence_source,
   criteria and protocol version; stable clause references use id or frozen contract
   hash/index when absent. Single sources self_rating/token_probability are supported;
   agreement needs multi_judge and is rejected for Single Judge (VI; A.6; I Chapter 3).
6. Judge verdict pass/fail plus finite numeric Confidence [0,1] is actionable at/above
   threshold, inconclusive below. Missing/invalid Confidence or protocol, transport
   failure, timeout or unmapped model yields oracle_unavailable; preserve raw response
   and any seen verdict in supporting evidence. One bounded call per assessment, no
   automatic re-attempts (permitted, not required). Multiple assertions require an
   assertions count >1 from the provider, otherwise an explicit atomic declaration
   (VI Single Judge, Confidence; C.7). No resolution/review/panel behavior in this slice.
7. Result records always include required C.7 fields, no null Confidence; optional
   panel/assertions/resolves/invalidated_by are absent unless applicable. Immutable
   history survives restart/live deletion; no API can overwrite a Result (C.7–C.8).
8. Admission validates all C.3 fields, versioned Reference Set, reviewer list, positive
   items, closed verdict keys/nonnegative totals, raw agreement, finite chance measure
   and threshold consistency. Only a Person with review records it; read is separate.
   Generated id/time/actor are rejected as input; latest accepted record determines
   admission, including withdrawal and not_computed=false (VI Admission; C.3–C.4).

### Unclear points
AMBIGUITIES entries 12–17 describe target/expected formats, composition, Custom
Validator registration, identity/assertions, malformed Judge outputs and Admission.
Tests cover every numbered rule, including earlier-slice behavior and real HTTP Judge.

## Slice 3 — Completed Work

### What was built
- `engine/validators.py`: pure built-in checks over selected frozen Evidence, explicit
  target/expected formats, local-only JSON Schema and a restricted declarative Custom
  Validator evaluator. Schema validation uses pinned jsonschema 4.23.0.
- `engine/assessment.py`: automatic Validation-before-Evaluation pipeline, cheapest-first
  Constraint evaluation, AND/OR/hard-veto handling, unavailable short-circuiting, Single
  Judge HTTP calls, Confidence-qualified dispositions, assertion-count disclosure and
  stable Oracle/clause identities.
- `engine/models/assessment.py`: consistent C.7 Result shape and strict C.3 Admission
  input validation. Confidence is numeric or not_applicable, never null.
- SQLite append-only Result/Admission stores and immutable project-local Custom
  Validator definitions; versioned rules are frozen before calls. Latest Admission is
  determined by acceptance order and later nonadmission withdraws earlier admission.
- Authenticated Admission and Custom Validator API, paginated/filterable Results,
  complete Judge protocol/startup URL mapping and documented registration examples.

### Required changes to earlier behavior
- Successful Execution POST now waits for assessment and its Results endpoint returns
  actual Results, as Volume V and C.7 require. Execution status/duration still describe
  Evidence collection; failed collection is never assessed. Historical slice-2 Executions
  are not automatically replayed or modified. One slice-2 test's empty-Results assertion
  was updated to check the now-required unavailable Result for its old invalid structural
  placeholder rule; all remaining earlier tests were retained.
- Preflight now rejects unsupported composition, Single Judge agreement Confidence,
  identical subject/Judge model, and execution of Human Review/Multi Judge Expectations
  (deferred to slice 5). Definition schemas for future capabilities are unchanged.
- New `configuration.validators` freezes registered rule bindings with runtime Evidence.
  Provider transport, subject wire protocol and recorded Execution immutability are unchanged.

### Tests and results
- `python -m pytest -q`: **168 passed**, Python 3.12.1; all 73 earlier cases (one required
  assertion update above), plus 95 new cases in `tests/test_assessment.py`.
- Tests cover all eight planned rules: pure built-ins and targets; malformed/missing
  checks; recorded latency/cost and cheapest-first order; composition/veto/unavailable
  blocking; Custom registration, governance, immutable/frozen version bindings; correct
  Judge request and self-rating/token probability Confidence; low/boundary/high Confidence;
  assertions; malformed/absent Confidence and protocol fields; transport/429/redirect/
  timeout/invalid JSON; no retries; immutable Results and Admission history; identity;
  strict Admission required/generated fields, consistency, permissions, Person-only
  action, acceptance order/withdrawal; real loopback HTTP Judge and SQLite restart.
- `git diff --check` passes. One existing Starlette/httpx deprecation warning remains.
- New ambiguities: **12–17** (formats, composition, registration, identity/assertions,
  unavailable Judge output, Admission). No external/conformance test material accessed.

### Deliberate limits, SHOULDs and deferred work
- Tool-call and Boundary Validators require action_boundary, explicitly excluded by
  BRIEF §3; applying them is unavailable rather than a silent pass.
- Multi Judge, Human Review, resolution/reassess, Gate/Release enforcement and control
  confirmation/invalidation stay in their designated later slices. Low Confidence is
  stored as inconclusive; no later-slice routing or verdict is invented.
- Custom registration implements a pure declarative interface, not arbitrary executable
  plugins or a public language SDK. Its evaluator has only target Evidence and frozen
  configuration inputs, satisfying the SDK's input-isolation SHOULDs.
- Cheapest-first uses fixed built-in cost classes and declaration order within ties;
  custom checks run last. No empirical timing/clock affects Validator ordering.
- Oracle transport re-attempts are MAY, deliberately not used: one bounded attempt is
  recorded. Malformed/unavailable output remains auditable without a replacement call.
- Reference Set scoring/provenance is supplied by the recording Person; Admission does
  not run an automatic scoring workflow. Human independence, blind labels, excluded
  alignment/exposed items, arbitration reasoning and multiple sources are documented
  authoring SHOULDs that the engine cannot verify from the C.3 aggregate record. A
  versioned reference_set is required. No known in-scope MUST is deliberately skipped.

## Slice 2 — plan

### Entities and operations
- Execution batch: authenticated `POST /projects/{project}/executions` with `suite` and
  `environment`; one Execution per Scenario × pinned dataset row (or one for fixed
  Variables/Evidence). Read metadata, Conversation, Artifacts and empty Results via
  Appendix C §C.2–C.4; paginated/filterable execution list (§C.6).
- Execution: immutable completed record containing IDs, timestamps, status, frozen
  Scenario, Environment, effective Contract, resolved settings, Variables, row identity,
  scheduling decision, attempts and errors (Volume III Runtime, Scheduling, Retry).
- Conversation: `{turns: [{prompt, response}]}`. Context is a private accumulated
  transcript; the deterministic continuation prompt is `Continue.` when the provider
  explicitly returns `complete: false` (Volume III Variables, Context, Conversation Engine).
- Artifacts: provider auxiliary data plus locally measured per-call latency and usage,
  captured on receipt; retained partial evidence is never assessed (Artifact Collection).

### Rules and references
1. Preflight the entire batch before any call: resolve existing Suite/Environment,
   versioned rows, all placeholders, effective Contracts and provider mapping. Reject
   missing inputs, unsupported scheduling and invalid durations (III Pipeline, Variables;
   A.4, A.9; C.1). Deterministic interpolation uses documented canonical JSON for nonstrings.
2. Resolve Project defaults and Suite overrides field by field, replacing RetryConfig as
   a field; default sequential, one worker, 30s timeout, no retry (A.9; ambiguity 7).
3. Log trigger actor/time, ordering, row, settings and configuration before running;
   sequential follows Scenario and row declaration order, parallel uses a bounded pool
   with private deep-copied state and preserves output order (III Scheduling, Parallelization).
4. Retry only infrastructure failure before any genuine Response in the Execution;
   preserve every attempt/error. `max_attempts` is a maximum retry count per A.9.
   Exhaustion and whole-Execution timeout yield infrastructure failure, no Conversation
   for assessment; never retry after a Response, including later-turn failure (III Retry,
   Timeouts). Keep partial turns separately for diagnosis.
5. Runtime freezes Environment/configuration, Variables and effective Contract; identical
   input yields identical prompt and provider conditions, independent of worker placement
   (III Runtime, Variables; I Chapter 4). No distributed topology is required.
6. A completed run supplies exactly one Conversation; multi-turn next prompt and finish
   logic are deterministic. Capture returned Artifacts/usage and observed latency per
   call. Fixed Evidence bypasses the subject and copies its Conversation/Artifacts into
   the same batch and Environment (III Pipeline, Context, Conversation Engine, Collection).
7. Persist evidence in SQLite independently of live configuration deletion; completed
   records have no update/delete API. Reads require `read`, triggers `execute`; errors
   name reasons; lists support offset/limit and suite/environment/status/date filters
   (C.3, C.4, C.6, C.8). No assessment, resolution or control confirmation in this slice.
8. Load and validate identifier-to-HTTP(S)-URL mapping once at app creation from
   `AQEF_PROVIDER_URLS`; no URL in AQEF configuration. Missing mapping rejects preflight;
   malformed startup settings fail startup. Subject wire protocol is fully specified in
   PROVIDERS.md (BRIEF §4; III Runtime).

### Unclear points
Entries 7–11 in AMBIGUITIES.md record defaults/inheritance, batch/wire shape,
multi-turn/retry boundaries, evidence on failure, and canonical variable rendering.
Each numbered rule above will have unit/API coverage; the whole earlier suite must pass.

## Slice 2 — Completed Work

### What was built
- `engine/execution.py`: batch preflight and expansion, frozen runtime configuration,
  deterministic prompt rendering and continuation, private Context/Variables, sequential
  and bounded parallel scheduling, retry histories and total execution deadlines.
- `engine/providers.py`: startup identifier-to-URL mapping validation, HTTP subject
  transport and strict response envelope. PROVIDERS.md now defines the exact wire
  protocol, PowerShell startup example, mapping lifecycle and failure behavior.
- `engine/api/executions.py`: authenticated execution trigger/list/metadata, Conversation,
  Artifacts and empty Results endpoints. Pagination and common execution filters included.
- SQLite runtime history persists independently of live configuration and across restart;
  scheduling decisions are written before calls and terminal records reject replacement.
- Fixed Evidence is validated and supplied without invoking the subject; confirmation,
  assessment and downstream decisions remain in their designated later slices.

### Earlier behavior changed because the specification requires it
- ExecutionConfig now serializes only supplied fields. Previously SQLite serialization
  materialized omitted values as null/defaults, losing field presence and breaking A.9's
  field-by-field inheritance. Explicit values (including explicit null for preflight
  rejection) are preserved. No earlier tests or governance behavior were changed.
- Direct dependencies are pinned to the installed, tested versions as BRIEF §4 requires.
  Existing LICENSE and the untracked owner-supplied AGENTS.md are left untouched.

### Tests and results
- `python -m pytest -q`: **73 passed** on Python 3.12.1, comprising all 42 pre-existing
  cases and 31 new cases in `tests/test_execution.py`.
- Coverage includes all eight planned rules: real loopback HTTP integration and SQLite
  restart; strict wire/settings validation; authentication/permissions; row expansion;
  preflight with no side effects; immutable history/deletion survival; canonical rendering;
  settings inheritance/repeatability; sequential/parallel pool bounds and state isolation;
  retry budget/exhaustion; malformed envelopes after a real Response; multi-turn Context;
  timeout across turns; HTTP 429/redirect/malformed JSON; fixed Evidence; pagination/filters.
- One installed Starlette/httpx deprecation warning remains; it does not affect results.
- New ambiguity entries: **7–11**. No conformance test material was accessed.

### Deliberate limits and SHOULDs
- No distributed worker topology: the specification permits a single-process Minimal
  Engine. Scheduling is on-demand sequential/parallel; unrecognized strategies are
  rejected instead of interpreted as cadence or priority syntax.
- No acting tools/Action Boundary, nonstatic sources, assessment or Decision behavior.
  Results are empty until slice 3. Control confirmation/invalidation is slice 5.
- Fixed Evidence source_execution is retained when supplied; the engine does not invent
  provenance when absent (A.4 SHOULD). Callers remain responsible for supplying recently
  captured Evidence from the same Environment.
- Execution POST is synchronous. A process crash may leave a queued/running diagnostic
  record; there is no automatic replay on restart, which could replace a real Response
  whose receipt was interrupted. Remote provider work cannot be undone on local timeout.

## Slice 1 — Plan

### 1. Overview
Slice 1 ("Foundation and Definition") implements the foundational entities, governance, security, and static configuration definitions of the AQEF engine. It provides the core data structures, storage, validation rules, approval workflows, and REST API endpoints required before any runtime execution or evaluation can occur.

---

### 2. Entities & API Resources to Implement

#### 2.1 Governance & Security
1. **Principal** (`Person` or `ServiceAccount`)
   - `id`: unique string identifier
   - `kind`: `"person"` or `"service_account"`
   - `name`: string
   - `email`: string
   - `team_ids`: list of Team IDs
   - `roles`: list of Role names
   - `owner_person_id`: string (MUST be present for `service_account`, MUST be null for `person`)
2. **Team**
   - API: `GET /teams`, `POST /teams`
   - Fields: `id`, `name`, `description`
3. **Role & Permission**
   - API: `GET /roles`, `POST /roles`
   - Role fields: `name`, `permissions` (list of permission strings)
4. **Approval Record**
   - API: `GET /projects/{project}/approvals`
   - Fields: `id`, `project`, `action` (`contract_define`, etc.), `target_resource`, `requested_by`, `approved_by`, `status`, `created_at`, `details`
5. **Audit Log**
   - API: `GET /projects/{project}/audit`
   - Fields: `id`, `project`, `action`, `principal_id`, `principal_kind`, `timestamp`, `details`

#### 2.2 Domain Entities & Configuration
6. **Project**
   - API: `GET /projects`, `POST /projects`, `GET /projects/{project}`, `PUT /projects/{project}`, `DELETE /projects/{project}`
   - Fields: `name`, `environments`, `suites`, `execution`, `datasets`, `defect_classes`, `contracts`, `quality_gates`
7. **Environment**
   - API: `GET /projects/{project}/environments`, `POST /projects/{project}/environments`, `GET /projects/{project}/environments/{env}`, `PUT /projects/{project}/environments/{env}`, `DELETE /projects/{project}/environments/{env}`
   - Fields: `name`, `model_version`, `prompt_version`, `tool_configuration`, `action_boundary`, `infra_target`
8. **Suite**
   - API: `GET /projects/{project}/suites`, `POST /projects/{project}/suites`, `GET /projects/{project}/suites/{suite}`
   - Fields: `name`, `scenarios`, `contracts`, `quality_gates`, `execution`
9. **Scenario**
   - API: `GET .../scenarios/{scenario}`, `POST .../scenarios`, `PUT .../scenarios/{scenario}`, `DELETE .../scenarios/{scenario}`
   - Fields: `name`, `contract`, `prompt`, `dataset`, `variables`, `seeded_control`, `evidence`
10. **Static Dataset**
    - API: `GET /projects/{project}/datasets`, `POST /projects/{project}/datasets`, `GET /projects/{project}/datasets/{dataset}`, `GET /projects/{project}/datasets/{dataset}/rows`, `POST /projects/{project}/datasets/{dataset}/versions`
    - Fields: `name`, `version`, `source` (`"static"` in scope for Slice 1), `rows` (list of `Row(id, variables)`)
11. **Quality Contract & Reusable Contract**
    - API: `GET /projects/{project}/contracts`, `POST /projects/{project}/contracts`, `GET /projects/{project}/contracts/{contract}`, `PUT /projects/{project}/contracts/{contract}`
    - Fields: `name`, `constraints`, `expectations`, `policies`, `extends`
12. **Quality Gate**
    - API: `GET /projects/{project}/gates`, `POST /projects/{project}/gates`, `PUT /projects/{project}/gates/{gate}`
    - Fields: `name`, `aggregate`, `threshold`, `compare_against`, `min_basis`, `on_failure`, `override_requires`, `require_admitted_judges`

---

### 3. MUST and MUST NOT Rules with Section References

#### 3.1 Governance, Authentication, and Permissions
- **[Spec Front-Matter §10; Volume XII §Principals; Appendix C §C.4]**
  - All API operations MUST be authenticated with a token resolving to a Principal.
  - A Service Account MUST have an owning Person accountable for what it does.
  - A Service Account MUST NOT be set up to look like a Person (`kind` must accurately distinguish `person` from `service_account`).
  - Permissions MUST be checkable independently of any Role that happens to include it.
  - Every mutating operation MUST check the resolved Principal's Permissions before executing. If permissions are missing, the API MUST reject the request (HTTP 403 Forbidden).
  - Automation (Service Account) may carry out a decision a person made; it MAY NOT make one.
  - `contract_define` MAY be applied by a Service Account only when approved by a Person in an external review; the approval record MUST name that Person and reference the external review.
  - Creating or changing a `contract`, `contracts`, or `quality_gates` value, on whatever resource (Project, Suite, or Scenario), is `contract_define` and MUST be governed and audited under `contract_define` **[Appendix C §C.5; Appendix B §B.3]**.

#### 3.2 Projects & Environments
- **[Appendix A §A.1; Appendix B §B.2]**
  - A Project MUST have a unique non-empty `name`.
  - A Project MUST define at least one Environment in `environments`.
- **[Appendix A §A.2; Appendix B §B.2, §B.3]**
  - An Environment `name` MUST be unique within the Project.
  - An Environment MUST define `model_version`, `prompt_version`, `tool_configuration`, and `infra_target`.
  - When `tool_configuration` is not null, `action_boundary` MUST be declared **[Appendix B §B.2, §B.3]**.
  - `tripwire: true` on a BoundaryEntry is valid ONLY when `kind` is `stub` **[Appendix B §B.2]**.
- **[Appendix C §C.8]**
  - `DELETE` on an Environment, Dataset, or Contract still referenced by an existing entity, Baseline, Snapshot, or Report MUST be rejected or preserved as a frozen historical record, never silently broken.
  - `DELETE /projects/{project}` MUST NOT be permitted while the Project has Baselines, Reports, or audit records unless the caller explicitly requests retention or deletion is separately authorized.

#### 3.3 Suites & Scenarios
- **[Appendix A §A.3; Appendix B §B.2]**
  - A Suite `name` MUST be unique within the Project.
  - A Suite MUST contain at least one Scenario.
  - A Quality Gate name MUST be unique across the Project and its Suites **[Appendix A §A.3; Appendix B §B.3]**.
- **[Appendix A §A.4; Appendix B §B.2, §B.3]**
  - A Scenario `name` MUST be unique within its Suite.
  - A Scenario MUST specify either `dataset` or `variables` (or neither); it MUST NOT specify both.
  - When a Dataset is referenced, it MUST be formatted as `name@version`. A reference without a version MUST NOT be accepted.
  - A Scenario MUST carry `prompt` unless its `dataset` is `production_replay` or it carries `evidence`.
  - A prompt template referencing a Variable that is not supplied by the Scenario's `variables` or every row of its Dataset MUST be rejected before execution starts **[Appendix A §A.4; Appendix B §B.3]**.
  - Fixed Evidence (`evidence`) MAY appear only on a Seeded Control with `confirmed_by: construction`, and then is REQUIRED. It MUST NOT carry `prompt`, `dataset`, or `variables` **[Appendix A §A.4; Appendix B §B.2, §B.3]**.
  - `planted_defect` is REQUIRED when `kind` is `defect` or absent, and MUST NOT appear when `kind` is `clean` **[Appendix B §B.2]**.
  - `difficulty_prior` MUST NOT appear on a clean control, and MUST NOT default to `0.0` (absent means `"not_established"`) **[Appendix A §A.4; Appendix B §B.2]**.
  - `confirmation` is REQUIRED when `confirmed_by` is `validator` and MUST NOT appear otherwise **[Appendix B §B.2]**.

#### 3.4 Quality Contracts & Composition
- **[Volume VII; Appendix A §A.5; Appendix B §B.2, §B.3]**
  - A Contract with zero Constraints and zero Expectations is invalid (MUST contain at least one Constraint or Expectation).
  - An Expectation MUST specify exactly one of `judge`, `multi_judge`, or `human_reviewer`.
  - An Expectation with `judge` or `multi_judge` MUST specify `confidence_threshold` (Float 0.0–1.0).
  - A Constraint MUST NOT specify a `confidence_threshold` (a Validator carries no Confidence).
  - When `on_timeout` is `escalate`, `escalate_to` is REQUIRED; otherwise `escalate_to` MUST NOT appear **[Appendix B §B.2]**.
  - A Constraint bound to a Custom Validator MUST declare `dimension` **[Appendix B §B.3]**.
  - A clause `id` MUST be unique within the Contract that declares it **[Appendix B §B.3]**.
- **[Volume VII — Contract Composition; Appendix B §B.3]**
  - Contract Composition is additive across contributing Contracts (Project, Suite, Scenario, and `extends`).
  - Two contributed clauses are the same clause only when they declare the same `id`. Identical content is one clause; differing content is an explicit composition conflict that MUST be surfaced and rejected, never silently resolved.
  - A lower level adds clauses but cannot remove or weaken a clause contributed by a higher one.
  - A clause without an `id` is never the same clause as another: it is added and applies alongside whatever was contributed.
  - For every Scenario in every Suite, the effective Contract resulting from composition MUST contain at least one clause.

#### 3.5 Datasets
- **[Volume IV; Appendix A §A.8; Appendix B §B.2, §B.3]**
  - Every Dataset MUST be versioned.
  - Dataset source for Slice 1 is restricted to `"static"`.
  - When `source` is `"static"`, `rows` is REQUIRED.
  - Each Row MUST have a unique `id` and a `variables` mapping.
  - Two configurations referencing the same Dataset `name` + `version` MUST resolve to identical rows. Any attempt to modify an existing version MUST be rejected (immutability).

#### 3.6 Quality Gates
- **[Appendix A §A.10; Appendix B §B.2, §B.3]**
  - A Gate `name` MUST be unique across the Project and all its Suites.
  - `aggregate` MUST be specified (`safety`, `functional`, `semantic`, `operational`, `regression`, etc.).
  - `on_failure` MUST be specified as `block_release` or `warn`.
  - If `min_basis` is declared, at least one of `results` or `scenarios` MUST be present.

#### 3.7 ExecutionConfig (Retry and Timeout)
- **[Appendix A §A.9; Appendix B §B.2, §B.3]**
  - In `RetryConfig`, `on` MUST be strictly `infrastructure_failure`. Any other value MUST be rejected.

---

### 4. Unclear Points (Recorded in `docs/AMBIGUITIES.md`)
1. **Approval Workflow Mechanism for `contract_define`**: Direct execution with inline approval logging for Persons with permission; required `approved_by` (Person) and `external_review_reference` for Service Accounts.
2. **Dataset Version Immutability**: Dataset versions are strictly immutable. Registering the same name and version twice returns a 409 Conflict.
3. **Contract Composition Conflict**: Any difference in attributes between clauses sharing an `id` is surfaced as an explicit composition conflict error.
4. **Project Deletion with History**: Deleting a project with history requires explicit `retain_history=true` parameter or admin override.
5. **Bearer Token Authentication**: Tokens mapped to Principals in database/store; requests without valid token rejected with 401.

---

## Slice 1 — Completed Work

### What was built:
1. **Repository Layout**:
   - `engine/models/`: Domain schemas for Principals, Teams, Roles, Projects, Environments, Suites, Scenarios, Datasets, Quality Contracts, Quality Gates, and ExecutionConfig.
   - `engine/storage.py`: SQLite-backed persistence layer for all configuration entities, approvals, audit logs, and referential integrity tracking.
   - `engine/auth.py`: Bearer token authentication, role/permission resolution, and governance side effects enforcement for `contract_define`.
   - `engine/composition.py`: Contract Composition implementation (additive composition, clause identity via `id`, conflict detection, and effective contract derivation).
   - `engine/validation.py`: Load-time semantic cross-type validation (Independent Oracles identity rule, dataset resolution, gate uniqueness, prompt variable interpolation).
   - `engine/api/`: REST API endpoints for Projects, Environments, Suites, Scenarios, Datasets, Contracts, Gates, Teams, Roles, Principals, Approvals, and Audit logs.
   - `engine/main.py`: FastAPI application entrypoint with idempotent bootstrap logic.
   - `docs/`: `IMPLEMENTATION_NOTES.md`, `AMBIGUITIES.md`, `PROVIDERS.md`, `API.md`.
2. **Tests**:
   - `tests/test_governance.py`: Tests for Principals, Service Accounts, Roles, Permissions, and `contract_define` governance.
   - `tests/test_contracts_composition.py`: Tests for Contracts, Constraints, Expectations, and additive Contract Composition with conflict surfacing.
   - `tests/test_domain_validation.py`: Tests for Project, Environment, Suite, Scenario, Seeded Control, Dataset versioning, MinBasis, and Independent Oracle rules.
   - `tests/test_api.py`: Integration tests for all Slice 1 REST API endpoints.
   - Total: 39 tests passing (100% pass rate).

### Deviations from SHOULD-level requirements:
- None. All applicable MUST, MUST NOT, and SHOULD requirements for Slice 1 scope were fully implemented.


