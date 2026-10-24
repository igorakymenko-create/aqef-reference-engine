# AQEF Conformance Statement — scope and qualifications

Issued 2026-10-24 for **AQEF Reference Engine, slice-8**, Python 3.12 / FastAPI /
SQLite, one self-hosted application process. Specification target: the bundled
**AQEF Working Draft 0.41.3**. Release source ref is `0.41.3` in the upstream AQEF
repository; the local ignored `spec/` kit has the updated normative texts. Exact
retrieved paths and source blob IDs are in [SPECIFICATION-SOURCES.json](SPECIFICATION-SOURCES.json).
Published 0.41.2 adopts owner decisions O-1/O-2 already implemented here; 0.41.3 adds
uncomputed-aggregate reasons, dimension Gate coverage and pre-run SHOULD checks.

```yaml
aqef_conformance:
  specification_version: "0.41.3"
  implementation: "AQEF Reference Engine slice-8"
  capabilities:
    - human_review
    - multi_judge
    - seeded_controls
  not_offered:
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

**Qualification of the claim:** the capabilities above describe the offered scope
to be checked. This engine is **not presently asserted to satisfy every applicable
MUST/MUST NOT**. The review found open core and coverage gaps below, so an unqualified
claim that the engine is AQEF-conformant would be false. Publishing this statement
and passing local unit tests do not prove Conformance (§10). This statement makes no
claim about the quality or conformance of an AI subject, person, Team or organization.

## Implementation-defined choices and locations

| Choice / normative source | Declared behavior | Documentation |
|---|---|---|
| Serialization and schema (A introduction, B) | REST JSON; no YAML/TOML file loader. Unknown AQEF configuration keys rejected. Some governance DTOs permit extra fields; primitive coercion/runtime schema gaps remain G3. | [API](API.md), code-derived [OpenAPI](OPENAPI.json), review G3 |
| Prompt placeholders (A.4) | `{{name}}` / `{{ name }}`; deterministic one-pass interpolation; nonstrings compact sorted-key JSON. Missing Variables rejected before calls. | [PROVIDERS](PROVIDERS.md#subject-request), ambiguities 9/11 |
| Runtime scheduling (III, A.9) | Sequential/parallel; declared Scenario/row output order, isolated Context/Variables; suite overrides project field by field. Local process only. REST trigger is synchronous, discrepancy G7. | [API](API.md#slice-2-execution-api), PROVIDERS, ambiguity 8/31 |
| Durations and bounds (III, A.9; VI) | Positive decimal ms/s/m/h and positive ISO day/time durations; defaults 30s subject-collection budget, no retries, one worker. Each Judge call gets a fresh execution.timeout budget (default 30s), after conversation collection completes; assessment is outside the Volume III Execution deadline. `max_attempts` counts retries after initial subject call. | PROVIDERS, API, ambiguities 7/11/16/33 |
| Subject/Judge adapters (BRIEF §4, VI) | One HTTP POST per call; exact model identifier mapped once at startup using `AQEF_PROVIDER_URLS`. No implicit credentials, endpoint suffixes or hidden criteria. Closed Judge verdict/confidence/explanation/assertions response. | [PROVIDERS](PROVIDERS.md), examples of mapping and both wire formats |
| Validator inputs/expected (V, A.5) | Evidence target paths; documented schema/pattern/sequence/latency/cost forms. Parameterless Custom Validator expected is `null` or `{}`; all other forms rejected at load naming clause. | API built-in formats and registration; ambiguities 12/14/19 (owner O-1/O-2) |
| Consensus/Confidence (VI, A.7) | Voting majority/unanimous/ceil fraction; weighted Boolean pass mean; mean/min own Confidence as documented, agreement separate; full quorum default. Preserve returned member verdicts on unavailable recovery. | PROVIDERS panel section, API panel section, ambiguity 25 |
| Human routing (VI, A.5) | Direct Human and unresolved consensus pending; Single inconclusive explicitly reviewable. Default 24h routing timeout; block/escalate without fabricated verdict. Designated Role and captured-Confidence policy enforced. | API Human sections, ambiguity 26 |
| Controls/prior/requalification (VIII, A.1/A.4/A.9) | One batch/Scenario entry with per-Oracle detail; confirmation precedes inference; unknown prior is not_established; strict fresh-control qualification. Missing Oracle verdict leaves control outcome invalid, interpretation 27. | API control sections; ambiguities 27–29; review includes limits |
| Authentication/authorization (C.4, XII) | Bearer token to stored Person/Service Account. Bootstrap Person uses AQEF_ADMIN_TOKEN or admin-token. Runtime and system/docs routes authenticate; ordinary actions check atomic permissions. Team/wildcard scope gap G1 remains. | API authentication and operation inventory; review G1 |
| Approval realization (XII, §10) | Authorized Person's call records immediate approval/audit; Service contract change needs X-Approved-By Person and X-External-Review-Ref. Baseline/override Person-only. Service release requires in-force Person-approved scoped policy. | API, ambiguity 1, decision examples |
| Pagination/filtering (C.6) | All collection lists use offset=0, limit=100, range 1–1000, plain JSON arrays. Filters limited to documented query fields. G2 was closed during this review. | API operation schemas/inventory, review G2 correction |
| Gate formula/thresholds (I Ch.6, A.10/A.12) | Positive Contract weights on actionable Boolean verdicts, dimension means; supported dimension/resource/overall/regression thresholds and min/max maps declared. Empty basis never silently passes. | API Gate examples, ambiguities 20/21 |
| Identity and historical scope (C.7/C.8; X) | Canonical JSON Oracle identity; SHA256 clause/Contract content references; scope freezes full inline Contracts. Explicit Baseline Result ID. Resolution append-only except pending Human completion retaining recorded_at. | API, ambiguities 15/22/23/28 |
| Deletion (C.8) | Reject referenced Environment deletion; Project deletion with history requires explicit retain_history=true, keeps frozen Execution/decision/governance records. No history-purge API. | API status/retention notes; ambiguity 4; storage/history tests |
| Report format (XI, C.10) | Frozen batch Reports, six always-present signal lists, full low_confidence denominators, nested panel member evidence; no dashboard/KPI front end. | API Report examples, ambiguity 20, review U1 |

Implementation choices do not authorize exceptions to mandatory rules. Where a
choice's completeness is disputed or unproven it appears in the review as a finding.

## Deliberate SHOULD deviations and limits

| Source | Deliberate deviation / reason |
|---|---|
| I Ch.3 / A.6 independent family and failure modes | No model-family registry/attestation or correlated-failure detector. Operators choose independent families. The B.3 identifier-identity MUST is enforced; external weights/aliases cannot be inferred from identifiers and are not attested by the engine. |
| I lifecycle feedback; VIII maintainability | Engine stores outcomes and governed changes but does not generate Requirements/Risk revisions from failures. Those are author decisions; the required rationale is not enforced (review U1). |
| VII narrow single-assertion authoring | Free-form criteria may cover multiple assertions; provider explicitly declares count. Semantic decomposition is left to authors rather than guessed from text. |
| VI Admission Reference Set provenance | No blind multi-reviewer labelling workflow, calibration-item exclusion, forced multi-source sets, arbitration creation, tuner-exposure ledger or automatic scoring service. API records versioned Reference Set identifiers, reviewer identities and arbitration references supplied by a Person. Independent human labelling remains external authoring work. |
| VIII coverage/generation/exposure | Controls are not automatically generated/required for every gated Oracle; hand-authored controls are accepted. No blind-review UI, rotating generator, surface-diversity policy or tuner/authorship segregation is enforced. Ordinary permissions alone cannot prove exposure independence. |
| VIII placement/source/confirmation timing | No guarantee a prompt plant survives into subject Evidence; failed confirmations remain invalid. Fixed Evidence source_execution is optional and not verified for recent/same-Environment derivation. Human confirmation may be late, with derived invalidation and fresh Gate evaluation thereafter. |
| C.6 filtering | Execution and Result filters exist; audit lacks date/Team filters and Baselines lack scenario/environment filters. Small implementation keeps records available through paginated unfiltered reads. G2 pagination was fixed, not waived as a SHOULD. |
| A/B/C generated artifacts | OpenAPI is generated from actual FastAPI models/operations and published as documentation; no independent complete schema generation from prose or generated SDK/CLI is supplied. Runtime schema completeness remains G3. |
| III Execution Pipeline (0.41.3), Judge reachability only | No availability-only provider operation exists; synthetic Evidence would obtain a real verdict and cannot guarantee later reachability. No reachability probe or proceed flag is offered. Suite/Gate warnings are implemented before subject invocation. |

Cheapest-first built-in Validation, pure Custom Validator inputs without clock/random/
network, controls before ordinary assessments, fail-fast affected Oracle suppression,
zero-reference-prior Human confirmation, and finite Human routing timeouts are
implemented. These are not claimed as skipped SHOULDs. SHOULDs conditional on an
unoffered capability (such as Production Replay privacy, generated-source independence
or Boundary hard vetoes) do not describe an offered implementation feature.

## Clarified rules met in slice 8

| Former finding / source | How the rule is met |
|---|---|
| G4 — B.3 Independent Oracle — identity | Judge model identifiers are checked against Environment model_version at configuration load/change and execution preflight, including panel members and reusable Contracts. Identical identifiers are rejected; different identifiers do not attest external weights. The family SHOULD remains a declared deviation. See validation.validate_contract_identity/validate_oracle_identity and test_slice_8.py::test_g4_b3_identity_rejects_subject_model_and_accepts_distinct_identifiers / ::test_g4_b3_identity_is_checked_before_subresource_configuration_changes. |
| G8 — III Execution Pipeline / Timeouts; VI Judge calls | “An Execution is complete once the Conversation Engine has no further turns to produce”; Validation/Evaluation follow separately. The subject deadline covers turns/retries. Each Judge has its own bounded call as declared above, not the remaining subject budget. test_slice_8.py::test_g8_iii_execution_completes_before_vi_judge_uses_own_timeout checks both a verdict after the subject deadline and a Judge timeout without changing completed Evidence. |

## Known gaps and verification

The complete rule-level table, test/module links and each UNTESTED/PARTIAL coverage
finding are in [CONFORMANCE-REVIEW.md](CONFORMANCE-REVIEW.md). Open gaps are:

- **G1:** Team access scopes and administrative wildcard authorization.
- **G3 / U1:** incomplete formal runtime schemas and per-property/negative test coverage;
  permissive primitive coercion/null acceptance in some configuration models.
- **G5:** inherited composition policy weakening not rejected/tested.
- **G6:** accepted Dataset mechanism semantics only; base_dataset version/reference validation is implemented.
- **G7:** synchronous REST trigger versus C.3 asynchronous execution wording.
- **U1:** every individual UNTESTED or PARTIAL/U1 ledger row remains a finding, including
  semantic authoring obligations, KPI traceability coverage and required-field matrices.

Review finding G2 (older-list pagination) was repaired in slice 6 and is not an open gap.

This statement cannot provide a passing external conformance result, independent
certification, verifiable external model ancestry, a complete MUST-coverage proof, or
assurance about undisclosed provider behavior. None is invented. No AQEF conformance
test material was accessed. The local whole suite passes **426 tests**, with one
Starlette/httpx deprecation warning; the suite is regression evidence only.

The statement applies to the source published under tag `slice-8`; it does not assert
that arbitrary deployment settings or later changes preserve these properties.
