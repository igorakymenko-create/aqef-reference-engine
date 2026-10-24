# AQEF Conformance Statement

Issued 2026-10-24 for **AQEF Reference Engine, slice-11**, Python 3.12 / FastAPI /
SQLite, one self-hosted application process. Specification target: the bundled
**AQEF Working Draft 0.41.5**. Release source ref is `0.41.5` in the upstream AQEF
repository; the local ignored `spec/` kit has the updated normative texts. Exact
retrieved paths and source blob IDs are in [SPECIFICATION-SOURCES.json](SPECIFICATION-SOURCES.json).
Published 0.41.2 adopted O-1/O-2; 0.41.3 added Gate reasons/coverage and pre-run SHOULDs.
0.41.4 settles synchronous triggering, audit, Team binding, policy composition and
scoped Dataset mechanisms. Slice 10 repaired null/unknown-key handling. Published
0.41.5 settles schema-artifact scope and author rationale, and explicitly requires
full B.2/B.3 validation on every configuration change, implemented in slice 11.

```yaml
aqef_conformance:
  specification_version: "0.41.5"
  implementation: "AQEF Reference Engine slice-11"
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

**Conformance claim:** AQEF Reference Engine, tag **slice-11**, claims **AQEF
Conformance to Working Draft 0.41.5** for `human_review`, `multi_judge` and
`seeded_controls`, with the non-negotiable core implicit. The prior classification-(a)
findings are closed by the implementation and the 0.41.5 clarifications documented
below. Known verification work (b) is not an assertion of an unmet MUST; deliberate
SHOULD deviations are declared separately. This claim is based on the specification
and implementation review, with local and owner-reported external evidence, not a
required percentage of test coverage. Conformance is a property of this implementation,
not of an AI subject, Person, Team or organization (§10).

**Team binding (XII Teams; §10): this engine binds no Projects or Suites to Teams.**
Every Principal's resource scope is every Project, regardless of Team membership.
Atomic Permissions, designated Human Roles, Person-only decisions and standing policy
rules still apply; scope is not permission. Team objects/memberships remain metadata.

The capability identifiers state the scope of this claim; they do not exempt any
applicable MUST. No additional capability is claimed.

## Implementation-defined choices and locations

| Choice / normative source | Declared behavior | Documentation |
|---|---|---|
| Serialization and schema (A introduction, B) | REST JSON; no YAML/TOML file loader. Unknown AQEF configuration keys rejected. Numbers reject numeric strings/booleans/nonfinite values; configuration Boolean flags reject coercion. Typed optional nulls and unknown governance keys are rejected. GET/live storage omit absent fields; explicitly nullable/free JSON values survive. OpenAPI is documentation, not an AQEF JSON Schema artifact; all resulting configurations receive B.2/B.3 checks. | [API](API.md), code-derived [OpenAPI](OPENAPI.json), classification below |
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
| I lifecycle feedback | No automatic Requirements/Risk generation from failures; authoring decisions remain external. VIII 0.41.5 assigns justification to the Project owners; the required engine Approval Workflow is implemented, not skipped. |
| VII narrow single-assertion authoring | Free-form criteria may cover multiple assertions; provider explicitly declares count. Semantic decomposition is left to authors rather than guessed from text. |
| VI Admission Reference Set provenance | No blind multi-reviewer labelling workflow, calibration-item exclusion, forced multi-source sets, arbitration creation, tuner-exposure ledger or automatic scoring service. API records versioned Reference Set identifiers, reviewer identities and arbitration references supplied by a Person. Independent human labelling remains external authoring work. |
| VIII coverage/generation/exposure | Controls are not automatically generated/required for every gated Oracle; hand-authored controls are accepted. No blind-review UI, rotating generator, surface-diversity policy or tuner/authorship segregation is enforced. Ordinary permissions alone cannot prove exposure independence. |
| VIII placement/source/confirmation timing | No guarantee a prompt plant survives into subject Evidence; failed confirmations remain invalid. Fixed Evidence source_execution is optional and not verified for recent/same-Environment derivation. Human confirmation may be late, with derived invalidation and fresh Gate evaluation thereafter. |
| VIII / B.3 declared defect-class references | The SHOULD to name declared defect classes is not enforced as a load-time rejection; class labels remain author-managed strings. This is a deliberate recommendation deviation, not a missing MUST. |
| C.6 filtering | Execution and Result filters exist; audit lacks date/Team filters and Baselines lack scenario/environment filters. Small implementation keeps records available through paginated unfiltered reads. G2 pagination was fixed, not waived as a SHOULD. |
| A/B/C generated artifacts | OpenAPI is generated from actual FastAPI models/operations and published as documentation; no independent complete schema generation from prose or generated SDK/CLI is supplied. No AQEF JSON Schema artifact is published or claimed. Its generation is a skipped SHOULD; runtime shapes remain documented and constrained as required. |
| III Execution Pipeline (0.41.5), Judge reachability only | No availability-only provider operation exists; synthetic Evidence would obtain a real verdict and cannot guarantee later reachability. No reachability probe or proceed flag is offered. Suite/Gate warnings are implemented before subject invocation. |

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

## Classification at 0.41.5

**No classification-(a) finding remains in this review.** The three slice-10 findings
close as follows; verification-only (b) work remains listed individually in the ledger.

| Former finding | Source, implementation and evidence | Current outcome |
|---|---|---|
| G10-LOAD / D-9 | B introduction (0.41.5): property constraints B.2 and cross-type B.3 apply on every operation that loads/changes configuration. storage._validate_configuration_change builds the resulting Project and proposed registry overlay under the configuration lock, reparses the B.2 model tree and calls validation.validate_project_configuration, also checking registered Dataset bases and unused reusable extends. Startup uses the same guard. test_slice_11.py::test_0415_b_every_configuration_route_validates_whole_result_before_any_write covers 16 mutation routes, with byte-for-byte database equality on rejection; ::test_d9_b2_b3_new_invalid_scenario_rejected_on_every_containing_route covers both reviewed violations; ::test_0415_b_resulting_parent_cardinality_and_coverage_are_enforced; ::test_0415_b_validation_uses_resulting_registry_and_allows_repair; ::test_0415_b_initial_load_rejects_legacy_semantically_invalid_project; ::test_0415_b_project_deletion_has_no_resulting_live_project_but_preserves_history; ::test_0415_b3_prompt_variables_are_complete_at_load_not_after_acceptance covers fixed Variables completeness. | Closed by implementation. No silent accepted configuration change; repair is evaluated against the proposed result, not an unchanged prior state. Project deletion leaves no live configuration and retains C.8 checks/history. |
| G3-FORMAL | B introduction (0.41.5): the MUSTs about “a conformant JSON Schema” bind that published artifact; B.1 does not require runtime records/responses to be formal schema types. **This engine publishes OpenAPI as API documentation, not as an AQEF JSON Schema artifact. It publishes and claims no such artifact.** Dynamic response documentation is not advertised as complete formal types. Runtime input constraints and A/C response shapes remain obligations, implemented/traced in the review. | Closed by the published clarification. JSON Schema artifact generation is a deliberately skipped SHOULD, not a waived runtime MUST. |
| G10-RATIONALE | VIII Test Maintainability (0.41.5): justification duty belongs to the people owning the Project; the engine's part is Approval Workflow. auth.enforce_governed_contract_define and normalized governed_values enforce Contract/Gate value changes across all definition routes. test_slice_11.py::test_0415_viii_xii_contract_changes_have_person_approval_and_service_review; ::test_0415_viii_every_contract_change_checks_contract_define_permission; ::test_0415_viii_service_contract_change_requires_existing_person_and_review exercise ten Contract-carrying operations with Person/Service success and denied permission, missing review, unknown/non-Person approver. Buffered contract_define approvals/audit persist only after success. | Closed by clarification and confirmation. Every Contract definition/change is approved by a Person and recorded; Service changes name that Person and external review. Author motivation/rationale is not inferred. Ambiguity 37 is closed. |

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
not a blanket non-conformance finding. The prior (a) findings are closed under 0.41.5; no qualification is retained
merely for incomplete regression matrices. Finishing every local coverage matrix is not the condition §10 sets.

## Owner-reported external evidence

The project owner supplied the aggregate outcome of **CTS WD8, AQEF 0.41.4,
run `r261024104303`** against slice 9:

| Result | Cases | Owner's supplied detail |
|---|---:|---|
| PASS | 162 | No engine defect found. |
| FAIL | 2 | Both findings are against test text: it expected a rejection to name a changed Gate/Contract, which the specification does not require. |
| NOT_RUN | 11 | Inspection/Declaration items; two cases the harness could not drive (crashing Custom Validator, multi-assertion Judge), and a mechanisms-based case made capability-scoped by 0.41.4. |
| NOT_APPLICABLE | 30 | Capabilities not claimed. |

The owner also supplied **CTS WD9, AQEF 0.41.4, run `r261024112524`** against
`slice-10`:

| Result | Cases | Owner's supplied detail |
|---|---:|---|
| PASS | 171 | No failures found. |
| FAIL | 0 | None. |
| NOT_RUN | 9 | Eight Inspection/Declaration items and one crashing Custom Validator case the engine could not be driven to. |
| NOT_APPLICABLE | 32 | Unclaimed capabilities and Team binding, which this engine does not have. |

Both runs are owner-reported evidence against earlier releases at 0.41.4, not a new
external run against slice 11/0.41.5 or independent certification. Only the supplied
summaries were used; no CTS material was requested, fetched, inspected or used.

This statement cannot provide independent certification, verifiable external model
ancestry, a complete MUST-coverage proof, or assurance about undisclosed provider behavior. None is invented. No AQEF conformance
test material was accessed. The local whole suite passes **769 tests**, with one
Starlette/httpx deprecation warning; the suite is regression evidence only.

The statement applies to the source published under tag `slice-11`; it does not assert
that arbitrary deployment settings or later changes preserve these properties.
