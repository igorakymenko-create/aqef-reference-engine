# AQEF Conformance Statement — scope and qualifications

Issued 2026-10-24 for **AQEF Reference Engine, slice-10**, Python 3.12 / FastAPI /
SQLite, one self-hosted application process. Specification target: the bundled
**AQEF Working Draft 0.41.4**. Release source ref is `0.41.4` in the upstream AQEF
repository; the local ignored `spec/` kit has the updated normative texts. Exact
retrieved paths and source blob IDs are in [SPECIFICATION-SOURCES.json](SPECIFICATION-SOURCES.json).
Published 0.41.2 adopted O-1/O-2; 0.41.3 added Gate reasons/coverage and pre-run SHOULDs.
0.41.4 settles synchronous triggering, audit, Team binding, policy composition and
scoped Dataset mechanisms. G1/G5/G6/G7 remain closed. Slice 10 repairs optional null
and request unknown-key handling, and separates implementation gaps from verification.

```yaml
aqef_conformance:
  specification_version: "0.41.4"
  implementation: "AQEF Reference Engine slice-10"
  capabilities:
    - human_review
    - multi_judge
    - seeded_controls
  not_offered:
    - dataset_mechanism:data_mutation
    - dataset_mechanism:fuzzing
    - dataset_mechanism:edge_cases
    - dataset_mechanism:adversarial
    - dataset:synthetic
    - dataset:generated
    - dataset:production_replay
    - action_boundary
    - cli
    - reference_ui
    - plugins:validator
    - plugins:judge
    - plugins:dataset
    - plugins:report
```

No `test_type:<name>`, `ci_cd:<platform>` or `sdk:<language>` capability is claimed
for any name/platform/language. General Scenarios can express different Contracts;
this is not a claim to ship Volume IX's named test-type implementations. Custom
Validators use the documented pure declarative registration interface (Volume V),
not executable Validator Plugins (Volume XVI) or a language SDK (Volume XIV).

The core is implicit, **not** a capability identifier in the list (§10). Static
Datasets are part of that core. Definition, Execution, Evidence, Assessment and
Decision are implemented; ordinary Results pass through Confidence handling before
aggregation. Topology is a deployment choice and removes no normative obligations.

**Qualification of the claim:** the engine **does not yet claim AQEF Conformance**
for the offered capabilities below at 0.41.4. The remaining classification-(a) findings
are the B.1/B.2 formal type definitions, a possible Requirements/Risk justification
obligation, and uneven Scenario-reference/reference-Oracle validation on subresource
changes. These are concrete source/code issues; **missing tests alone are not
non-conformance**. Verification-only findings (b) are listed separately and do not
withhold a claim by themselves (§10). The external run is evidence, not a waiver of
applicable MUSTs. No claim concerns an AI subject, person, Team or organization.

**Team binding (XII Teams; §10): this engine binds no Projects or Suites to Teams.**
Every Principal's resource scope is every Project, regardless of Team membership.
Atomic Permissions, designated Human Roles, Person-only decisions and standing policy
rules still apply; scope is not permission. Team objects/memberships remain metadata.

The capability identifiers describe the offered surface to be checked. They do not
turn the remaining implementation gaps into permitted exceptions.

## Implementation-defined choices and locations

| Choice / normative source | Declared behavior | Documentation |
|---|---|---|
| Serialization and schema (A introduction, B) | REST JSON; no YAML/TOML file loader. Unknown AQEF configuration keys rejected. Numbers reject numeric strings/booleans/nonfinite values; configuration Boolean flags reject coercion. Typed optional nulls and unknown governance keys are rejected. GET/live storage omit absent fields; explicitly nullable/free JSON values survive. G3-FORMAL remains as detailed below. | [API](API.md), code-derived [OpenAPI](OPENAPI.json), review G3 |
| Prompt placeholders (A.4) | `{{name}}` / `{{ name }}`; deterministic one-pass interpolation; nonstrings compact sorted-key JSON. Missing Variables rejected before calls. | [PROVIDERS](PROVIDERS.md#subject-request), ambiguities 9/11 |
| Runtime scheduling (III, A.9) | Sequential/parallel; declared Scenario/row output order, isolated Context/Variables; suite overrides project field by field. Local process only. C.3 response mode is synchronous completion: 201 includes identifier, Executions and warnings. This is implementation-defined in 0.41.4 (former G7). | [API](API.md#slice-2-execution-api), PROVIDERS, ambiguity 8/31 |
| Durations and bounds (III, A.9; VI) | Positive decimal ms/s/m/h and positive ISO day/time durations; defaults 30s subject-collection budget, no retries, one worker. Each Judge call gets a fresh execution.timeout budget (default 30s), after conversation collection completes; assessment is outside the Volume III Execution deadline. `max_attempts` counts retries after initial subject call. | PROVIDERS, API, ambiguities 7/11/16/33 |
| Subject/Judge adapters (BRIEF §4, VI) | One HTTP POST per call; exact model identifier mapped once at startup using `AQEF_PROVIDER_URLS`. No implicit credentials, endpoint suffixes or hidden criteria. Closed Judge verdict/confidence/explanation/assertions response. | [PROVIDERS](PROVIDERS.md), examples of mapping and both wire formats |
| Validator inputs/expected (V, A.5) | Evidence target paths; documented schema/pattern/sequence/latency/cost forms. Parameterless Custom Validator expected is `null` or `{}`; all other forms rejected at load naming clause. | API built-in formats and registration; ambiguities 12/14/19 (owner O-1/O-2) |
| Consensus/Confidence (VI, A.7) | Voting majority/unanimous/ceil fraction; weighted Boolean pass mean; mean/min own Confidence as documented, agreement separate; full quorum default. Preserve returned member verdicts on unavailable recovery. | PROVIDERS panel section, API panel section, ambiguity 25 |
| Human routing (VI, A.5) | Direct Human and unresolved consensus pending; Single inconclusive explicitly reviewable. Default 24h routing timeout; block/escalate without fabricated verdict. Designated Role and captured-Confidence policy enforced. | API Human sections, ambiguity 26 |
| Controls/prior/requalification (VIII, A.1/A.4/A.9) | One batch/Scenario entry with per-Oracle detail; confirmation precedes inference; unknown prior is not_established; strict fresh-control qualification. Missing Oracle verdict leaves control outcome invalid, interpretation 27. | API control sections; ambiguities 27–29; review includes limits |
| Authentication/authorization (C.4, XII) | Bearer token to stored Person/Service Account. Bootstrap Person uses AQEF_ADMIN_TOKEN or admin-token. Runtime and system/docs routes authenticate; ordinary actions check atomic permissions. No Project/Suite Team bindings; every Principal scope is every Project. Bootstrap administrative Role enumerates atomic Permissions; neither the Role name nor an admin Permission is a wildcard (former G1). | API authentication and operation inventory; review G1 |
| Approval realization (XII, §10) | Authorized Person's call records immediate approval/audit; Service contract change needs X-Approved-By Person and X-External-Review-Ref. Baseline/override Person-only. Service release requires in-force Person-approved scoped policy. | API, ambiguity 1, decision examples |
| Pagination/filtering (C.6) | All collection lists use offset=0, limit=100, range 1–1000, plain JSON arrays. Filters limited to documented query fields. G2 was closed during this review. | API operation schemas/inventory, review G2 correction |
| Gate formula/thresholds (I Ch.6, A.10/A.12) | Positive source-Contract clause weights on actionable Boolean verdicts, dimension means; supported dimension/resource/overall/regression thresholds and min/max maps declared. Empty basis never silently passes. | API Gate examples, ambiguities 20/21 |
| Identity and historical scope (C.7/C.8; X) | Canonical JSON Oracle identity; SHA256 clause/Contract content references; scope freezes full inline Contracts. Explicit Baseline Result ID. Resolution append-only except pending Human completion retaining recorded_at. | API, ambiguities 15/22/23/28 |
| Deletion (C.8) | Reject referenced Environment deletion; Project deletion with history requires explicit retain_history=true, keeps frozen Execution/decision/governance records. No history-purge API. | API status/retention notes; ambiguity 4; storage/history tests |
| Report format (XI, C.10) | Frozen batch Reports, six always-present signal lists, full low_confidence denominators, nested panel member evidence; no dashboard/KPI front end. | API Report examples, ambiguity 20, review U1 |

Implementation choices do not authorize exceptions to mandatory rules. Where a
choice's completeness is disputed or unproven it appears in the review as a finding.

## Deliberate SHOULD deviations and limits

| Source | Deliberate deviation / reason |
|---|---|
| I Ch.3 / A.6 independent family and failure modes | No model-family registry/attestation or correlated-failure detector. Operators choose independent families. The B.3 identifier-identity MUST is enforced; external weights/aliases cannot be inferred from identifiers and are not attested by the engine. |
| I lifecycle feedback | No automatic Requirements/Risk generation from failures; authoring decisions remain external. The separate VIII mandatory justification concern is classification (a), G10-RATIONALE, not waived as a SHOULD. |
| VII narrow single-assertion authoring | Free-form criteria may cover multiple assertions; provider explicitly declares count. Semantic decomposition is left to authors rather than guessed from text. |
| VI Admission Reference Set provenance | No blind multi-reviewer labelling workflow, calibration-item exclusion, forced multi-source sets, arbitration creation, tuner-exposure ledger or automatic scoring service. API records versioned Reference Set identifiers, reviewer identities and arbitration references supplied by a Person. Independent human labelling remains external authoring work. |
| VIII coverage/generation/exposure | Controls are not automatically generated/required for every gated Oracle; hand-authored controls are accepted. No blind-review UI, rotating generator, surface-diversity policy or tuner/authorship segregation is enforced. Ordinary permissions alone cannot prove exposure independence. |
| VIII placement/source/confirmation timing | No guarantee a prompt plant survives into subject Evidence; failed confirmations remain invalid. Fixed Evidence source_execution is optional and not verified for recent/same-Environment derivation. Human confirmation may be late, with derived invalidation and fresh Gate evaluation thereafter. |
| VIII / B.3 declared defect-class references | The SHOULD to name declared defect classes is not enforced as a load-time rejection; class labels remain author-managed strings. This is a deliberate recommendation deviation, not a missing MUST. |
| C.6 filtering | Execution and Result filters exist; audit lacks date/Team filters and Baselines lack scenario/environment filters. Small implementation keeps records available through paginated unfiltered reads. G2 pagination was fixed, not waived as a SHOULD. |
| A/B/C generated artifacts | OpenAPI is generated from actual FastAPI models/operations and published as documentation; no independent complete schema generation from prose or generated SDK/CLI is supplied. Runtime schema completeness remains G3. |
| III Execution Pipeline (0.41.4), Judge reachability only | No availability-only provider operation exists; synthetic Evidence would obtain a real verdict and cannot guarantee later reachability. No reachability probe or proceed flag is offered. Suite/Gate warnings are implemented before subject invocation. |

Cheapest-first built-in Validation, pure Custom Validator inputs without clock/random/
network, controls before ordinary assessments, fail-fast affected Oracle suppression,
zero-reference-prior Human confirmation, and finite Human routing timeouts are
implemented. These are not claimed as skipped SHOULDs. SHOULDs conditional on an
unoffered capability (such as Production Replay privacy, generated-source independence
or Boundary hard vetoes) do not describe an offered implementation feature.

## Clarified rules met in slices 8–9

| Former finding / source | How the rule is met |
|---|---|
| G4 — B.3 Independent Oracle — identity | Judge model identifiers are checked against Environment model_version at configuration load/change and execution preflight, including panel members and reusable Contracts. Identical identifiers are rejected; different identifiers do not attest external weights. The family SHOULD remains a declared deviation. See validation.validate_contract_identity/validate_oracle_identity and test_slice_8.py::test_g4_b3_identity_rejects_subject_model_and_accepts_distinct_identifiers / ::test_g4_b3_identity_is_checked_before_subresource_configuration_changes. |
| G8 — III Execution Pipeline / Timeouts; VI Judge calls | “An Execution is complete once the Conversation Engine has no further turns to produce”; Validation/Evaluation follow separately. The subject deadline covers turns/retries. Each Judge has its own bounded call as declared above, not the remaining subject budget. test_slice_8.py::test_g8_iii_execution_completes_before_vi_judge_uses_own_timeout checks both a verdict after the subject deadline and a Judge timeout without changing completed Evidence. |

## 0.41.4 rules met

| Former finding / source | How the rule is met |
|---|---|
| G7 — C.3 Triggering | Synchronous completion response is the documented choice, tested by test_slice_9.py::test_0414_c3_sync_trigger_returns_completed_executions_and_identifier. |
| XII Audit | Mutation-only records preserve Principal/kind, target/action/time and deletion intent. test_slice_9.py::test_0414_xii_audit_records_mutations_with_actor_and_not_reads and the complete D-8 mutation workflow confirm existing behavior. Historical pre-D-8 read entries remain legacy records; no new reads are recorded. |
| G1 — XII Teams/§10; C.4 | Binding-none scope declared above. Atomic authorization removes all admin shortcuts; bootstrap Role lists each Permission. Tests cover unrelated/no Teams, restricted admin Role, admin-only Permission, arbitrary-role governed actions and Service actor restrictions. |
| G5 — VII/A.5/B.3 | Strictest contributed mode, lower weakening conflicts at load/change including extends. Every source clause weight is frozen in runtime clause_weights and used by Gate/Report aggregation; changed repeated-ID weights conflict. Source-weight changes stale the affected named clause. Entry 36 documents peers/defaults. |
| G6 — IV/A.8/§10 | No mechanism capability offered. Every nonempty mechanisms list is rejected at load/change naming the field/type. Empty list means none. B.3 base references were already fixed in slice 8. |

## Remaining implementation gaps — classification (a)

These findings identify source/code mismatches, not absent unit tests:

| Finding | Normative text and evidence | Outcome |
|---|---|---|
| G3-FORMAL | B.1: “A conformant JSON Schema MUST define the following top-level types”; B.2: “For each type, the schema MUST enforce the following.” Baseline, ReleaseDecision, GateResult, Basis, Snapshot and ReleasePolicy are still dynamic dictionaries without their required formal type definitions. API prose/examples and correct constructed runtime values do not supply those definitions. engine/api/decision.py, engine/decision.py, docs/OPENAPI.json; ledger R230/R231/R263/R264/R265/R267/R268/R269. | (a), confirmed formal-schema gap. Artifact generation being SHOULD does not justify claiming a supplied incomplete schema meets B.1. Report's dynamic schema is also a documentation limitation, without inventing an extra B.1 Report type. |
| G10-RATIONALE | VIII Test Maintainability: a Contract loosened to stop a failing Suite “MUST be treated as a Requirements or Risk Analysis decision ... recorded and justified”. Contract PUT accepts a lower confidence_threshold under a generic Person approval without a justification or external review reference. auth.enforce_governed_contract_define and api/contracts.py do not require or retain a Requirements/Risk rationale when none is supplied. Ledger R071/R392; ambiguity 37. | (a), possible unmet obligation, conservative reading. Generic audit approval alone does not reconstruct a missing justification. Author motive cannot be inferred from criteria; no new intent detector/header format is invented here. |
| G10-LOAD — Scenario Dataset | B.3 Dataset reference requires Scenario.dataset to resolve when configuration loads. Full Project validation checks it; staged subresource writes check base_dataset but not Scenario.dataset. A fresh Project followed by POST /projects/p/suites/s/scenarios with name=missing-dataset, prompt.template=hi, dataset=absent@1 returned 201 in the slice-10 prose-derived inspection. No provider call was made. validation.validate_project_configuration versus storage._validate_configuration_change; ledger R270/R314. | (a), confirmed uneven semantic validation across configuration routes. The slice-8 base_dataset fix remains valid; this is the Scenario-reference part of the broader old row. |
| G10-LOAD — reference Oracle | A.1/A.4 and B.3 difficulty-prior provenance require independence from the Oracle tested. Full Project validation rejects identical reference/tested identifiers. Adding a fixed-Evidence control by Scenario POST with tested model=judge-a, difficulty_prior=0.8, prior_basis=1, prior_source=reference_oracles and reference_oracles=[JudgeConfig(model=judge-a)] returned 201 in the same inspection. storage._validate_configuration_change omits the full Project reference-independence check; ledger R104/R107/R287. | (a), confirmed uneven validation. This does not reopen G4's distinct subject-versus-Judge identity check, which is enforced on writes. |

These inspections used only the local implementation and specification-derived data,
not external test material. The last two are reported rather than silently marked as
verification-only. This slice's requested engine correction is explicit-null/unknown-key
handling; the claim review explicitly permits remaining (a) findings to be listed.

## Known verification gaps — classification (b)

The complete per-row classification is in [CONFORMANCE-REVIEW.md](CONFORMANCE-REVIEW.md).
Rows labeled VERIFICATION b have implementation evidence but lack an individually
verified full regression matrix. This includes configuration property/required-field
matrices, runtime response fields, denied-workflow/permission branches, stored-Evidence
repeatability diagnostics, author-criteria semantics and conditional KPI traceability.
No test can establish the semantic adequacy of arbitrary author Requirements; that
does not by itself identify an unmet engine MUST. CLI is not offered; the old CLI
UNTESTED row is corrected to out of scope. The defect-class reference recommendation
is SHOULD-only and is recorded as a deliberate deviation, not an unmet MUST.

G3's optional-null/unknown-key components are repaired. G2, G4/G8 and G1/G5/G6/G7
remain closed as recorded in earlier slices. U1 is now a verification inventory,
not a blanket non-conformance finding. Only the concrete (a) findings above retain
the qualification. Finishing every local coverage matrix is not the condition §10 sets.

## Owner-reported external evidence

The project owner supplied the aggregate outcome of **CTS WD8, AQEF 0.41.4,
run `r261024104303`** against slice 9:

| Result | Cases | Owner's supplied detail |
|---|---:|---|
| PASS | 162 | No engine defect found. |
| FAIL | 2 | Both findings are against test text: it expected a rejection to name a changed Gate/Contract, which the specification does not require. |
| NOT_RUN | 11 | Inspection/Declaration items; two cases the harness could not drive (crashing Custom Validator, multi-assertion Judge), and a mechanisms-based case made capability-scoped by 0.41.4. |
| NOT_APPLICABLE | 30 | Capabilities not claimed. |

This is owner-reported external evidence, not an independent certification or a claim
that the two FAIL counts were passes. The run predates slice 10; no new external run
is asserted. Only this supplied summary was used: no test material was requested,
retrieved, inspected, or used to implement the engine. Local regression evidence for
the null/omission changes is reported separately.

This statement cannot provide independent certification, verifiable external model
ancestry, a complete MUST-coverage proof, or assurance about undisclosed provider behavior. None is invented. No AQEF conformance
test material was accessed. The local whole suite passes **657 tests**, with one
Starlette/httpx deprecation warning; the suite is regression evidence only.

The statement applies to the source published under tag `slice-10`; it does not assert
that arbitrary deployment settings or later changes preserve these properties.
