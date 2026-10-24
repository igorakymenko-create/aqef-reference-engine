# Ambiguities Log

## 25. Panel Confidence and unavailable members
- **Section:** VI Consensus/Voting/Confidence; A.7; C.7.
- **Quotation:** “not ... a substitute for a Judge's own stated Confidence”; “panel ... counted”.
- **Readings:** use vote fraction as Confidence or retain member uncertainty separately;
  treat unavailable members as fails or block absent assessment.
- **Choice:** voting Confidence is the minimum own Confidence among winner voters;
  confidence_weighted_mean uses confidence-weighted pass scores, mean own Confidence,
  and separately declared agreement. Never replace own Confidence with agreement.
  No response is a vote. Missing availability without control exclusion blocks as
  oracle_unavailable when quorum is otherwise met; control exclusions below quorum
  yield not_assessed. Only voting/confidence_weighted_mean are supported methods.
  Member agreement confidence_source requests self_rating on the wire and retains the
  configured source in identity; agreement is reported separately.
  Unavailable-panel recovery preserves already returned verdicts and retries only
  members that failed before any verdict, including when malformed Confidence made
  the overall response unavailable. It cannot solicit a replacement for a real vote.

## 26. Human routing and timeout defaults
- **Section:** VI Human Review; A.5; C.3/C.7.
- **Quotation:** “MAY instead be routed”; “block ... leaves ... blocking”; “escalate ... Role”.
- **Readings:** automatically route every low-confidence Judge or expose the explicit
  review endpoint; make timeout fabricate unavailable versus remain awaiting_review.
- **Choice:** direct Human Expectations and unresolved consensus route automatically;
  low-confidence Single Judge remains inconclusive and explicitly reviewable (MAY route).
  Consensus Human fallback requires review permission without inventing a named Role,
  with optional numeric Confidence, because A.7 supplies no Role. Default timeout is
  24h; explicit review_timeout overrides it. After
  expiration block is marked timed_out while still blocking; escalate changes required
  Role to escalate_to, preserving the Result and requiring an actual Person's verdict.
  Routing/timer metadata is derived, not written onto immutable pending Results.

## 27. One control Scenario, several Oracles and dataset rows
- **Section:** VIII Seeded Controls; C.3 Seeded Control Reporting.
- **Quotation:** “one entry per Seeded Control Scenario”; “same Oracle ... shares that class”.
- **Readings:** one scalar outcome hides differing Oracle results; duplicate control
  entries violate the one-per-Scenario shape.
- **Choice:** one batch/Scenario record with per-Oracle details and Result IDs, plus the
  required scalar summary (any false_alarm/missed dominates invalid; invalid dominates
  passed/caught). Invalidation uses only per-Oracle confirmed misses. Every dataset row
  must confirm the control's declaration; unconfirmed rows make it invalid. A reached
  verdict below required Confidence does not demonstrate detection and is a miss.
  Control phases are serial before normal parallel work; halted records are cancelled
  without subject/Oracle invocation, not fake quality failures.
  Only clauses covering the control's class test that class. No verdict (pending review
  or unavailable transport) leaves the control's Oracle outcome invalid rather than
  inventing a failure. low_confidence denominators include member Results as well as the
  panel aggregate, with distinct Oracle identities; member Results are not double-counted
  in Quality aggregates.

## 28. Corrected Oracle selection and fresh requalification controls
- **Section:** VIII Requalification; C.3 reassess/requalifications.
- **Quotation:** “never the control it missed”; “for every defect class ... kind that failed”.
- **Readings:** trust supplied control IDs versus verify stored confirmed outcomes;
  accept any new model string versus an inspectable versioned configuration.
- **Choice:** oracle is the canonical JSON identity produced by the engine, including
  criteria/configuration; corrected configuration must assess the same frozen clause
  criteria/target and differ from the invalidated Oracle. Qualification controls may
  come from multiple fresh batches, but every ID must be caught/passed by that exact
  configuration. Freshness excludes every control Scenario and source_execution exposed
  by a miss in affected batches. Member Results are preserved with IDs inside panel
  supporting_evidence and can support member requalification. Qualification records
  are never themselves a license to reopen actionable Results.
  Identical captured Conversations are also exposed; fresh control scores must follow
  the confirmed miss, both when recording qualification and when using it for reassess.
  Cross-run quarantine follows VIII's until-requalified rule, while invalidated_by stays
  derived from misses in the Result's own run. Prior-run skips retain source control IDs.
  Corrected configuration preserves the frozen clause's target/expected or criteria;
  panels preserve purpose, sample/member count and Consensus/quorum. Weakening these
  requires a governed Contract change, not a reassessment shortcut. A corrected Human
  Oracle may change its designated Role after fresh controls establish it.

## 29. Difficulty prior provenance and zero-reference catches
- **Section:** VIII Difficulty prior; A.1/A.4.
- **Quotation:** “Same provenance rules”; “MUST state how many control instances”.
- **Readings:** per-control numeric override without basis fields versus explicit same
  provenance as class; allow prior 0 to gate versus require Human confirmation.
- **Choice:** add prior_basis/prior_source/reference_oracles to per-control override
  schema, require basis/source for numeric priors, check exact-model independence from
  tested Judges. Unknown prior is exposed as not_established. A numeric zero from
  reference_oracles cannot gate until a Person confirms the control, even if construction
  or Validator confirmed the Evidence. Priors are copied from configuration and never
  derived from the tested Oracle. Human independence/exposure beyond declared metadata
  is an authoring responsibility, recorded as an unverifiable SHOULD.

## 20. Decision batch scope and Report generation
- **Sections:** C.3 Gates/Reports; C.10; I Ch.6.
- **Quotation:** “Evaluate Gates against a set of Results”; “frozen when generated”.
- **Readings:** arbitrary client Result subsets versus a complete batch, implicit versus
  explicit report generation (C.3 lists Report reads but no generator path).
- **Choice:** check body names execution_batch_id, reads every effective Result of that
  Suite/Environment batch, rejects partial/in-flight evidence. POST /reports with that
  batch explicitly generates a frozen Report, evaluating applicable Gates if never
  evaluated or definitions changed. No client-supplied Results or Gate outcomes accepted.

## 21. Aggregate formula, ThresholdMap and empty basis
- **Sections:** I Ch.6 Aggregation; A.10/A.12.
- **Quotation:** “counted at face value”; “a property of that Gate's own configuration”.
- **Readings:** confidence discount after threshold, or weighted Boolean pass rate;
  empty aggregates implicitly pass versus not_computed.
- **Choice:** actionable pass=1/fail=0 weighted by positive Contract policies.weight
  (default 1); no second Confidence discount. Dimension scalar threshold is minimum pass
  rate. overall scalar combines dimension means equally. ThresholdMap keys may select
  dimensions, pass_rate, latency_ms, total_tokens or cost; numeric metric bounds are
  maxima for resource metrics, minima for pass rates. Bounds may be {min,max,weight}
  to state dimension-combination weight; unknown/empty/nonfinite forms rejected.
  No Evidence gives not_computed and insufficient_basis. Safety Validator failures veto
  independently. Missing applicable current clauses/results are insufficient_basis,
  never a fabricated Result. Regression threshold is maximum regression rate.

## 22. Snapshot versions and Baseline identity
- **Sections:** A.11/A.13; X Baselines and Snapshot Comparison.
- **Quotation:** “exact ... Contract version”; “which Baseline or Snapshot ... named Baseline”.
- **Readings:** mutable names as versions or content-addressed copies; first/multiple
  Results in an Execution designated implicitly versus explicit result_id.
- **Choice:** reusable versions are sha256 of canonical Contract content, stored with
  full contents; effective per-Scenario Contracts also frozen for deterministic clause
  comparison. Baseline POST requires execution_id and result_id; server adds id and
  approval metadata. Optional name is used for regression lookup. Latest accepted
  matching Baseline wins only with explicit latest_approved; Snapshot comparison uses
  its frozen Baseline IDs. Incompatible Oracle/clause or absent references are uncomputed
  comparisons rather than response text diffs. Baselines need not be passes, but must
  be effective actionable findings; pass->fail is the defined regression.

## 23. Resolution input and unavailable follow-up
- **Sections:** I Ch.6 Result Resolution; C.3/C.7.
- **Quotation:** “only ... current effective Result”; “same Oracle configuration”.
- **Readings:** allow arbitrary new Oracle on unavailable versus exact Oracle; create
  review workflow infrastructure now versus only the requested review endpoint.
- **Choice:** reassess requires exact frozen oracle string and unavailable effective
  state. Human review directly supplies verdict/supporting_evidence, optional numeric
  Confidence; absent means not_applicable. Only inconclusive or awaiting Human Review
  may be reviewed; a failed/available actionable verdict cannot be reopened. Full Human
  workflow routing/timeout/panels/requalification remain slice 5. Duplicate resolution
  links reject atomically; the awaiting_review completion preserves recorded_at.

## 24. Approval fields, report freshness and Service Account rejection
- **Sections:** XII Principals/Approval Workflow; A.12/A.14; C.3.
- **Quotation:** “Principal who recorded”; “configuration ... differs ... MUST NOT ... recorded”.
- **Readings:** trust supplied approved_by/role/time and gates, or derive from Principal
  and stored Report; allow old evaluations after more recent ones or require latest.
- **Choice:** server derives actor/role/time and Gate entries. Inputs specify batch,
  report_id, snapshot_id, decision, optional release_policy/notes. A Report must describe
  the latest evaluation for that batch and config must still match Snapshot, even for
  rejected decisions. User supplies no GateResult copies. Standing Policy revocation is
  a separate append-only event; historical policies/releases remain readable. Existing
  minimal direct Approval Workflow is reused, never a new admin exemption.

## 12. Built-in Validator target and expected formats
- **Section:** Volume V Built-in Validators; Appendix A §A.5.
- **Quotation:** “Structure varies by validator type”; “response, conversation, artifacts.*, or a specific path”.
- **Readings:** infer arbitrary formats, or publish precise supported deterministic formats.
- **Choice:** publish formats in API.md. Response is the last turn's response; conversation
  is the full object; artifacts.* is the complete list; artifacts.NAME selects matching
  data (one value or a list), with dotted paths/indexes supported. Missing evidence is
  unavailable. Schema applies a JSON Schema object/Boolean to the Evidence value as
  held, or `json` explicitly checks JSON syntax (**O-1, project-owner decision below,
  replaces the earlier implicit JSON decoding choice**); structural
  accepts a required_steps list (or `{required_steps:[...]}`), matched in order; latency
  accepts a duration or numeric milliseconds; cost a numeric maximum or metric/max map;
  forbidden-content accepts `{patterns:[string or {regex:string}]}`. Unsupported rules
  are unavailable rather than guessed passes. Schemas are local-only; remote refs rejected.

## 18. O-1 — Schema target instance (decided by the project owner)
- **Section:** Volume V, Built-in Validators — Schema Validator.
- **Quotation:** “checks a Response ... against an expected format or schema”.
- **Earlier choice (superseded):** implicitly decode every string target as JSON before
  applying a JSON Schema. This made an ordinary text Response impossible to validate
  against a nonempty string schema.
- **Owner's decision:** the instance is the target value exactly as Evidence holds it.
  A Response is a string: `{type: string, minLength: 1}` passes nonempty plain text and
  fails empty text. A JSON-looking Response remains a string under an object schema.
  `expected: "json"` explicitly checks JSON syntax, while a target path such as
  `response.some_key` explicitly decodes JSON during target selection and then applies
  the schema to that selected value. This replaces the earlier choice in entry 12;
  it applies equally to built-in and Custom schema rules.

## 13. Composition and short-circuit granularity
- **Section:** Volume V Execution Order, Composition, Validator SDK; Appendix A §A.5.
- **Quotation:** “AND”, “OR”, “hard veto”; “Validation has then not passed”.
- **Readings:** any individual fail immediately stops all checking; or finish Constraints
  and apply declared composition before deciding whether to invoke Judges.
- **Choice:** record all Constraint outcomes, cheapest-first, then apply policy. OR needs
  a passing Constraint; AND and hard-veto require all. A failed veto or any unavailable
  Constraint blocks regardless of OR. Empty Constraints pass vacuously. No fake skipped
  Judge Result uses not_assessed (C.7 reserves that for controls/quorum). Policies cannot
  silently bypass an unavailable check. hard-veto's undeclared base is conservatively AND.

## 14. Custom Validator registration
- **Section:** Volume V Custom Validators, Validator SDK; Appendix C §C.4.
- **Quotation:** “A Project MAY define Custom Validators”; “only inputs”; “not ... network access”.
- **Readings:** load arbitrary executable functions, or register restricted pure declarative
  rules. No registration path or permission is specified.
- **Choice:** project-local POST /validators (contract_define with existing governance),
  GET /validators (read). Immutable `{name,version,rule}` rules use a bounded declarative
  equality, pattern, schema or range evaluator; no code/clock/random/network access.
  Constraints bind `name@version` (bare name only if exactly one version exists). Built-in
  names cannot be shadowed. Registration is configuration, not a plugin or language SDK.
  A Custom Result's Oracle identity includes the rule; no silent version replacement.
  **Superseded by owner decision O-2 (entry 19):** Custom expected accepts null or {},
  and any other structure is rejected at load naming the clause.

## 19. O-2 — Custom Validator expected (decided by the project owner)
- **Section:** Appendix A §A.5, clarification announced for 0.41.2 by the project owner.
- **Owner decision:** “a structure it does not accept MUST be rejected when the
  configuration is loaded, naming the clause”; “accept expected: {} ... alongside null”.
- **Earlier choice (superseded):** only null, with unsupported values discovered during
  execution as oracle_unavailable.
- **Replacement:** the registered declarative rules have no per-Constraint parameters;
  null and an empty object are both documented valid forms. All other expected values
  fail Constraint schema validation at load on every configuration route, naming id
  or the validator/target pair for an unnamed clause. Execution keeps a defensive check
  for pre-existing frozen records, accepting both documented forms. No spec file edited.

## 15. Oracle and clause identity, assertions and agreement Confidence
- **Section:** VI Single Judge, Confidence, Admission; C.7; A.6.
- **Quotation:** “changed model, prompt, or criteria is a different Judge”; “assertions”.
- **Readings:** model name alone; or canonical model/source/criteria/protocol identity.
- **Choice:** canonical JSON Oracle string includes all Judge configuration and criteria,
  plus wire version. No hidden criteria prompt is added. Unnamed clause references include
  hash of frozen effective Contract, kind and index. Built-ins/custom identity includes
  version and expected rule. Judge response must declare integer assertions >=1; 1 is
  omitted from Result, >1 copied. The engine cannot infer semantic assertion count from
  free text; the provider must report it honestly. Single Judge agreement is rejected
  at preflight, since panel agreement cannot replace its own Confidence (VI Confidence).

## 16. Unavailable and malformed Judge responses
- **Section:** VI Judge Architecture, Confidence; C.7.
- **Quotation:** “MUST carry a Confidence value”; “Once any response carrying a verdict arrives, it stands”.
- **Readings:** invent Confidence, accept malformed output, or retain output as diagnostic
  evidence while recording no usable assessment.
- **Choice:** exact pass/fail, finite numeric [0,1] confidence, declared assertions and
  supporting explanation are required. Any invalid/missing field yields unavailable
  with null Result verdict and not_applicable Confidence; raw received verdict remains
  in supporting_evidence. One attempt only, bounded by the configured timeout as an
  assessment budget separate from the completed subject runtime. No second chance can
  replace an unfavorable/invalid response. Unknown Judge fields are rejected.

## 17. Admission input, acceptance order and reference provenance
- **Section:** VI Admission; C.3 Admission.
- **Quotation:** “Every other field is required except arbitrations”; “accepted last”.
- **Readings:** accept arbitrary verdict labels/provenance or restrict to pass/fail and
  identified Persons; constrain every named agreement measure to the same numeric range.
- **Choice:** verdict_distribution keys are pass/fail only (missing zero-count key allowed),
  labelled_by resolves to at least one existing Person; no role named reviewer is invented.
  Nonempty names/reference strings, finite numeric agreement/threshold; measures are
  Project-defined, so chance values/thresholds have no invented universal [0,1] range.
  Raw agreement is [0,1]. Most recent means SQLite insertion order, never client time.
  Preserve absent arbitrations versus empty. The API records supplied comparison evidence,
  not an automatic reference-set scoring service; provenance SHOULDs are documented.

## 7. Execution defaults and retry count
- **Section:** Appendix A §A.9; Volume III Timeouts, Retry.
- **Quotation:** “overridden at the Suite level field by field”; “Maximum retry count.”
- **Readings:** merge nested retry attributes or replace the retry field; count total
  attempts or retries after the initial call; unbounded or finite default timeout.
- **Choice:** replace explicitly supplied non-null Suite fields, including the whole
  RetryConfig. `max_attempts` counts retries, so total calls may be 1 + max_attempts.
  Defaults: sequential, parallelization 1, 30s whole-Execution timeout, zero retries.
  Reject null overrides and unsupported scheduling; these prevent silent unbounded runs.

## 8. Batch request, response and scheduling
- **Section:** Appendix C §C.3 Execution; Volume III Scheduling.
- **Quotation:** “Trigger Execution(s) for a Suite × Environment”; “logged and reproducible”.
- **Readings:** asynchronous jobs or a synchronous batch; arbitrary subset or whole Suite.
- **Choice:** POST accepts exactly `{suite, environment}`, runs the whole Suite and all
  rows in declared order, and returns `{execution_batch_id, executions}` after completion.
  Parallel mode limits concurrency and returns the same declaration order. Every record
  freezes scheduling reason, order, actor, configuration and trigger time before calls.
  No custom priority/cadence syntax is inferred; unknown strategies are rejected.

## 9. Conversation protocol and retry boundary
- **Section:** Volume III Variables, Conversation Engine, Retry.
- **Quotation:** “later turns are constructed by the Conversation Engine from Context”;
  “before the subject has produced a genuine Response”.
- **Readings:** single-turn only; invent a Scenario turn DSL; provider supplies a finish
  signal while the engine constructs deterministic continuation from transcript Context.
- **Choice:** provider returns a string `response`, optional Boolean `complete` (true
  by default), and optional artifact/usage data. For false, the next prompt is literally
  `Continue.` with the full preceding transcript in `context`. No acting tools execute.
  After any response string is received, no retry of that Execution is allowed, even
  if another field is invalid or a later turn fails. Unknown response fields are rejected.
  This preserves genuine unfavorable responses instead of replacing them.

## 10. Failed execution evidence and fixed evidence shape
- **Section:** Volume III Timeouts, Pipeline; Appendix A §A.4.
- **Quotation:** “produces no Conversation to assess at all”; “in the form the implementation stores Conversations”.
- **Readings:** discard partial traces, or retain diagnostics separately from assessable Evidence.
- **Choice:** failed runs expose no completed Conversation (409), but store partial turns,
  artifacts and attempts for diagnosis, never assessed. Fixed Conversation must be the
  same nonempty `{turns: [{prompt: string, response: string}]}` shape as live output;
  reject invalid fixed Evidence at batch preflight. Optional source_execution is retained;
  absence is allowed because provenance is SHOULD, and cannot be fabricated by the engine.

## 11. Placeholder values and runtime bounds
- **Section:** Appendix A §A.4; Volume III Variables, Timeouts.
- **Quotation:** “Placeholder syntax is implementation-defined”; “same literal Prompt text every time”.
- **Readings:** host-language string conversion or canonical JSON for nonstring Variables;
  per-attempt timeout reset or whole-Execution deadline across retries and turns.
- **Choice:** `{{ name }}` uses the existing alphanumeric/underscore syntax. Strings
  substitute literally; other JSON values use compact sorted-key UTF-8 JSON (no NaN).
  Substitution is one pass, without recursively interpreting inserted text. Durations
  accept positive decimal ms/s/m/h; timeout covers the entire Execution including retries
  and all turns, excluding scheduling wait. No new subject invocation after expiration.

This document records points in the AQEF specification (Working Draft 0.41.1) where the text allows more than one reading, following Rule 3 of the Implementer's Brief:
- Pick the more conservative reading (rejects more, blocks more, records more).
- Never decide an ambiguity silently.
- Record: Section, Quotation, Readings seen, Choice and rationale.

---

## 1. Approval Workflow Execution Mechanism for `contract_define`

- **Section:** Volume XII — Governance (§Approval Workflow, §Principals) & Appendix C §C.3, §C.5
- **Quotation:**
  > "Approval Workflow is the single mechanism — a request, review by someone holding an appropriate Role, an explicit approve-or-deny decision, logged for Audit and Traceability... Defining a Contract includes defining or changing a Quality Gate... A `contract_define` applied by a Service Account MUST name the approving Person and reference the external review." (Volume XII)
  > "Minimal Engine and Enterprise Engine... A Minimal Engine's single-click Approval Workflow and an Enterprise Engine's multi-Role review chain are equally conformant realizations of the same Governance requirement" (§10)
  > "`POST /projects/{project}/contracts`: Create a Contract. Governed by Approval Workflow. Permission: `contract_define`." (Appendix C §C.3)
- **Readings seen:**
  1. *Two-phase only:* Every `contract_define` operation MUST first be submitted as a pending Approval request to `/projects/{project}/approvals`, and cannot take effect until a separate approval call is made.
  2. *Direct execution with immediate approval record for Persons; explicit external review reference for Service Accounts:* A Person possessing `contract_define` calling `POST /contracts` or `POST /gates` acts as the approver; the engine verifies their permission, creates an Approval record (`status: approved`, `approved_by: <person_id>`), executes the change, and emits an Audit Log entry. A Service Account calling the endpoint MUST supply `approved_by` (naming a Person) and `external_review_reference`; otherwise the request is rejected.
- **Choice and rationale:** Reading 2 is chosen for the synchronous API, with the strict conservative constraint: if a Service Account attempts `contract_define` without an `approved_by` naming an existing Person and an `external_review_reference`, it is strictly rejected (HTTP 403/422). Furthermore, both an Approval record (in `/approvals`) and an Audit log entry (in `/audit`) are unconditionally recorded for every contract and gate mutation.

---

## 2. Dataset Version Immutability and Re-registration

- **Section:** Volume IV — Dataset Engine (§Versioning) & Appendix B §B.3
- **Quotation:**
  > "Two configurations referencing the same Dataset name + version MUST resolve to identical rows." (Appendix B §B.3)
  > "Every Dataset, regardless of source, MUST be versioned... A Scenario therefore references a Dataset by name and version, `name@version`, never by name alone." (Volume IV)
- **Readings seen:**
  1. *Overwrite allowed if rows match:* A `POST` with the same name and version could check if existing rows are byte-for-byte identical.
  2. *Strict immutability (immutable version key):* Once a Dataset `name@version` is created, any subsequent attempt to POST or register the exact same `name` and `version` is strictly rejected with a conflict (HTTP 409).
- **Choice and rationale:** Reading 2 (Strict immutability). Rejecting any re-creation prevents any race condition or silent divergence, ensuring reproducible Variable Resolution.

---

## 3. Contract Composition Clause Conflict Definition

- **Section:** Volume VII — Quality Contracts (§Contract Composition) & Appendix B §B.3
- **Quotation:**
  > "Two contributed clauses are the same clause only when they declare the same `id`. With identical content they are one clause; with differing content, such as two Confidence thresholds, they are a conflict. A clause without an `id` is never the same clause as another: it is added, and applies alongside whatever else was contributed... a lower level adds clauses but cannot remove or weaken a clause contributed by a higher one."
- **Readings seen:**
  1. *Permit compatible tightening:* A lower level could override a higher-level clause with a stricter threshold (e.g., increasing `confidence_threshold` from 0.7 to 0.8) without being considered a conflict.
  2. *Strict identity required on shared ID:* If two contributed clauses share the same `id`, they MUST be structurally identical across all properties. Any difference (whether looser or tighter) is treated as a composition conflict and rejected.
- **Choice and rationale:** Reading 2 (Strict identity). The spec states: "With identical content they are one clause; with differing content, such as two Confidence thresholds, they are a conflict... silently picking one value would hide exactly the kind of drift Chapter 3 requires a Contract to remain auditable against." Therefore, any difference in a clause with the same `id` is surfaced as an explicit composition conflict error.

---

## 4. Deletion of Project with Historical Data

- **Section:** Appendix C §C.8
- **Quotation:**
  > "`DELETE /projects/{project}` MUST NOT be permitted while the Project has Baselines, Reports, or audit records unless the caller explicitly requests their retention or their deletion is separately, explicitly authorized."
- **Readings seen:**
  1. Query parameter or header flag `force=true`.
  2. Explicit parameter `retain_history=true` or separate authorization permission `audit_delete` / `history_delete`.
- **Choice and rationale:** Conservative approach: By default, `DELETE /projects/{project}` MUST be rejected (HTTP 409 Conflict) if any Baselines, Reports, Snapshots, or Audit records exist. It is only permitted if the query parameter `retain_history=true` is passed (which cascades deletion of active entities while preserving frozen audit/history records) or if an explicit administrative override is passed by a principal holding `project_delete` and `audit_admin`.

---

## 5. Bearer Token Authentication Resolution

- **Section:** Appendix C §C.4 & Volume XII (§Principals)
- **Quotation:**
  > "All API operations MUST be authenticated. The authentication mechanism is implementation-defined (API key, OAuth 2.0, etc.) but MUST resolve to a Principal — a Person or a Service Account with an owning Person — with Team membership and Role assignments (Volume XII — Principals)."
- **Readings seen:**
  1. External OAuth/JWT server.
  2. Bearer token lookup table / database mapping tokens directly to Principal records, each with `kind` (`person` or `service_account`), `team_ids`, and assigned `roles` which map to granular `permissions`.
- **Choice and rationale:** Reading 2. In accordance with BRIEF.md §4 ("A bearer token per Principal is enough. Document how Principals, Teams, Roles, and Permissions are created"), the engine implements a token store where each Bearer token maps to a Principal entity. All requests without a valid `Authorization: Bearer <token>` are rejected with HTTP 401 Unauthorized.

---

## 6. Dataset Mechanisms on Static Datasets and Unknown Field Handling

- **Section:** Appendix A §A.8 (Dataset, MechanismConfig) & BRIEF.md §3, §10
- **Quotation:**
  > "`mechanisms` | List of MechanismConfig | MAY | Coverage mechanisms applied to this Dataset." (Appendix A §A.8)
  > "`type` | String | MUST | `data_mutation`, `fuzzing`, `edge_cases`, or `adversarial`." (MechanismConfig)
  > "A conformant implementation MUST accept configurations expressible within this specification" (Appendix A, intro)
- **Readings seen:**
  1. *Reject all mechanisms as out of scope:* Since BRIEF.md §3 limits scope to Static datasets and claims core, human_review, multi_judge, and seeded_controls, reject any dataset containing `mechanisms`.
  2. *Support MechanismConfig in data schema with strict validation of `type`, preserving mechanisms rather than dropping them, and reject unknown configuration keys across all models:* The specification explicitly permits `mechanisms` to be configured on Static datasets (Volume IV: "M -> DS (versioned)"). Thus, `mechanisms` is supported in Dataset configuration, enforcing the required `type` field (`data_mutation`, `fuzzing`, `edge_cases`, `adversarial`). A `MechanismConfig` missing `type` MUST be rejected with HTTP 422. Furthermore, in accordance with the requirement that fields are never silently dropped, all configuration models strictly forbid unknown keys (`extra='forbid'`).
- **Choice and rationale:** Reading 2. Rejecting invalid `MechanismConfig` (lacking `type`) and forbidding unknown keys across all configuration models guarantees strict compliance with Appendix A and Appendix B schemas, ensuring no configuration field is silently dropped.

