# AQEF Engine API Documentation

## Slice 4 — Decision and Release

All examples use `/projects/demo` and a bearer-authenticated Person with the endpoint's
atomic permission. IDs below are illustrative server-generated IDs. No request supplies
Results, copied Gate outcomes, approving actor/time or an administrative bypass.

### Evaluate Gates for a batch

POST `/projects/demo/gates/check`, permission execute:

```json
{"execution_batch_id":"batch-1"}
```

Response 200 (additional trace fields include id, evaluated_at, result_ids and admissions):

```json
{
  "id":"snapshot-1", "snapshot_id":"snapshot-1", "execution_batch_id":"batch-1",
  "evaluated_at":"2026-10-24T12:00:00+00:00", "result_ids":["result-1"], "admissions":{},
  "gates":{"functional":{"id":"gate-result-1","status":"pass","blocking":true,
    "value":1.0,"threshold":0.95,
    "basis":{"results":1,"not_actionable":0,"scenarios":1,"executions":1,"min_basis_met":"not_declared"}}}
}
```

The entire batch is used, not a client-selected favorable subset. All Project and its
Suite Gates are included. Confidence is applied first; effective actionable pass/fail
Results contribute 1/0 at face value, weighted by positive Contract policies.weight
(default 1). Safety Validator failure is a separate hard veto. Seeded Controls are
excluded. Missing evidence, unresolved Results, staleness and required-but-missing Judge
Admission cannot silently pass. Every applicable failure reason is reported in reasons;
reasons is absent on pass. Empty/uncomputed values are `"not_computed"`, never null.

Dimension aggregates are functional/semantic/safety/operational. Scalar threshold is a
minimum pass rate. overall scalar averages dimension means. ThresholdMaps select named
dimensions, pass_rate, latency_ms, total_tokens or cost; resource values are per-Execution
means with maximum numeric bounds. Other numeric bounds are minima (regression bounds
are maxima). Explicit bounds use `{"min":0.9,"max":1}`. For overall, a map can combine
dimensions at declared weights:
`{"functional":{"min":0,"weight":9},"semantic":{"min":0,"weight":1},"overall":0.9}`.
Weight must be positive and used with an overall bound; without overall, map entries
are independent sub-thresholds. ThresholdMap responses also provide metric_basis per
sub-metric so their individual denominators remain visible. Unsupported aggregates/metrics/bounds return 422.
Missing/uncomputed evidence is insufficient_basis, not an invented numerical failure.

Each evaluation captures an immutable Snapshot. GET `/snapshots` and `/snapshots/{id}`
require read. Explicit POST `/snapshots` requires snapshot_create, for example
`{"suites":["smoke"],"environments":["staging"],"release_label":"candidate-1"}`.
Response 201 contains id/captured_at/project/suites/environments/contracts (name→SHA256
version), inline_contracts (attachment→ordered full definitions), quality_gates and
baselines. Additional contract_contents/effective_contracts preserve the complete
content needed for reconstruction and clause matching. A changed clause id is stale;
an unchanged identified clause is current despite changes elsewhere in its Contract.
Unnamed clauses compare the whole effective Contract. Environment changes stale all
affected Results. Gates are re-evaluated against current definitions without refreshing
old Evidence. Changes outside the decision's Suite/Environment scope do not affect it.

### Generate and retrieve a frozen Report

POST `/projects/demo/reports`, execute, body `{"execution_batch_id":"batch-1"}`.
Response 201:

```json
{
  "id":"report-1","generated_at":"2026-10-24T12:00:01+00:00",
  "scope":{"project":"demo","suites":["smoke"],"environments":["staging"],"execution_batch_ids":["batch-1"]},
  "snapshot_id":"snapshot-1",
  "gates":{"functional":{"id":"gate-result-1","status":"pass","blocking":true,"value":1,
    "threshold":0.95,"basis":{"results":1,"not_actionable":0,"scenarios":1,"executions":1,"min_basis_met":"not_declared"}}},
  "metrics":[
    {"name":"functional.pass_rate","definition":"Contract-weighted actionable pass rate; Confidence applied before aggregation","value":1,"result_ids":["result-1"]},
    {"name":"semantic.pass_rate","definition":"Contract-weighted actionable pass rate; Confidence applied before aggregation","value":"not_computed","result_ids":[]},
    {"name":"safety.pass_rate","definition":"Contract-weighted actionable pass rate; Confidence applied before aggregation","value":"not_computed","result_ids":[]},
    {"name":"operational.pass_rate","definition":"Contract-weighted actionable pass rate; Confidence applied before aggregation","value":"not_computed","result_ids":[]}
  ],
  "signals":{"retries":[],"low_confidence":[],"multi_judge":[],"unenforced_boundaries":[],"boundary_attempts":[],"unadmitted_judges":[]}
}
```

GET `/projects/demo/reports/report-1` returns that exact frozen object; GET `/reports`
lists them. Generation uses the latest evaluation, evaluating if absent or when config,
effective Result standing (including awaiting_review completion with unchanged id) or
Admission state changed. Overrides are copied at generation;
an old Report never changes after a later override/resolution. Signals expose per-Scenario
retries, per-Scenario/Oracle inconclusive/total counts and every unadmitted Judge even
where a Gate does not require Admission. Panel/control reporting is deferred to slice 5.
Baseline comparison Metrics also include exact current/Baseline Result IDs and potential
prompt/model/dataset drift causes; these are correlations, not fabricated diagnoses.
Provider Artifacts named boundary_attempt (one object) or boundary_attempts (list), with
target/blocked/tripwire facts, are surfaced with their Execution IDs; this reports
recorded Evidence and does not enable acting tools or Action Boundary enforcement.

### Override exactly one failed blocking GateResult

POST `/projects/demo/gates/functional/override`, Person with gate_override and any
Gate-specific override_requires permission:

```json
{"gate_result_id":"failed-gate-result-2","execution_batch_id":"batch-1","justification":"Accept the documented risk for this candidate"}
```

Response 201:

```json
{"id":"failed-gate-result-2","gate":"functional","execution_batch_id":"batch-1",
 "justification":"Accept the documented risk for this candidate","approval_id":"approval-2",
 "approved_by":"reviewer","approved_at":"2026-10-24T12:01:00+00:00","approval_role":"release-reviewer"}
```

The GateResult stays fail; a newly generated Report/Release includes
`"override":"approval-2"`. Wrong Gate/id/batch is 404; passing/advisory/already-overridden
GateResults are 409. A new evaluation gets new IDs and inherits no override.

### Record a Release Decision

POST `/projects/demo/releases`, release_decide:

```json
{"execution_batch_id":"batch-1","report_id":"report-1","snapshot_id":"snapshot-1","decision":"approved","notes":"Reviewed candidate"}
```

Response 201:

```json
{"id":"release-1","project":"demo","environment":"staging","suite":"smoke",
 "execution_batch_id":"batch-1","report_id":"report-1","snapshot_id":"snapshot-1","decision":"approved","notes":"Reviewed candidate",
 "gates":{"functional":{"id":"gate-result-1","status":"pass","blocking":true,"value":1,"threshold":0.95,
 "basis":{"results":1,"not_actionable":0,"scenarios":1,"executions":1,"min_basis_met":"not_declared"}}},
 "approved_by":"reviewer","approved_at":"2026-10-24T12:02:00+00:00","approval_role":"release-reviewer","approval_id":"approval-3"}
```

At least one applicable Gate is required. approved requires every blocking Gate pass;
overridden requires an override on every failed blocking GateResult; rejected records
a negative decision. Advisory Gate failures remain visible and do not alone prevent
approval. Report/batch/Snapshot must match the latest evaluation; stale scoped config,
new effective Results, changed Admission or a later override require fresh evaluation/
Report (409). GET `/releases` and `/releases/{id}` return immutable history.

### Standing Release Policy

POST `/projects/demo/release-policies`, Person with release_decide:

```json
{"suites":["smoke"],"environments":["staging"],"service_accounts":["ci-bot"]}
```

Response 201:

```json
{"id":"policy-1","project":"demo","suites":["smoke"],"environments":["staging"],"service_accounts":["ci-bot"],
 "approved_by":"reviewer","approved_at":"2026-10-24T12:03:00+00:00","approval_role":"release-reviewer","approval_id":"approval-4"}
```

The Service Account must itself hold release_decide and add `"release_policy":"policy-1"`
to the Release request. Only approved (every blocking Gate pass without overrides) or
rejected is allowed. Policy must cover actor/Suite/Environment and be in force. Person-only
POST `/release-policies/policy-1/revoke` takes no fields; response 200 is the Policy plus
revoked_at/revoked_by. It authorizes no new decisions; previously recorded Releases stand.
GET collection/id includes revoked policies; no policy PUT/PATCH is provided.

### Explicit Baseline

POST `/projects/demo/baselines`, Person with baseline_approve:

```json
{"execution_id":"execution-1","result_id":"result-1","name":"release-reference"}
```

Response 201 includes the following fields, plus full frozen result/configuration/evidence:

```json
{"id":"baseline-1","name":"release-reference","suite":"smoke","scenario":"greeting","environment":"staging",
 "execution_id":"execution-1","result_id":"result-1","dataset":"greetings@1",
 "approved_by":"reviewer","approved_at":"2026-10-24T12:04:00+00:00","approval_role":"baseline-reviewer","approval_id":"approval-5",
 "result":{"id":"result-1","execution":"execution-1","clause":"shape","oracle_type":"validator","oracle":"schema-configuration","verdict":"pass","confidence":"not_applicable","disposition":"actionable","supporting_evidence":{},"recorded_at":"2026-10-24T11:59:00+00:00"},
 "configuration":{"environment":{"name":"staging","model_version":"subject-v1","prompt_version":"p1","tool_configuration":null,"action_boundary":null,"infra_target":"local"},"scenario":{"name":"greeting","prompt":{"template":"Hello"},"contract":null,"dataset":"greetings@1","variables":null,"seeded_control":null,"evidence":null},"contract":{"name":"effective_contract","constraints":[{"id":"shape","validator":"schema","target":"response","expected":{"type":"string"},"veto":false,"dimension":"functional","defect_classes":null}],"expectations":[],"policies":null,"extends":[]},"execution":{"timeout":"30s","scheduling":"sequential","parallelization":1,"retry":null},"validators":{}},
 "evidence":{"conversation":{"turns":[{"prompt":"Hello","response":"Hello!"}]},"artifacts":[]}}
```

The frozen configuration/result above illustrates nesting; actual values are copied
verbatim from the designated Execution/Result, including all resolved schema fields.
Baseline must reference a current effective actionable Result, never a control or
unfinished Execution. GET `/baselines` and `/baselines/{id}` retain approval and pinned
Dataset/Contract/Environment/Evidence. No run automatically updates a Baseline.
Regression Gate uses aggregate regression, maximum numeric regression-rate threshold
(ordinarily 0) and compare_against named Baseline/id, latest_approved or Snapshot id.
Only compatible Scenario/clause/Oracle comparisons are used; a missing comparison is
not_computed/insufficient_basis. Regression means baseline pass→current fail, never
literal response inequality. Explicit Snapshot baselines may freeze the chosen IDs.

### Result Resolution

POST `/executions/{execution}/results/{result}/review` with
`{"verdict":"pass","supporting_evidence":{"reason":"verified source"}}` requires a
Person with review and any clause human_reviewer.role. Optional numeric confidence is
supported; omit it when uncaptured, never send null. It resolves only the current
inconclusive Result; actionable/already-resolved/unavailable automated Results are 409.
The response is a new C.7 Human Reviewer Result with resolves, reviewing Person and time
in supporting_evidence. An awaiting_review Human Result instead completes in place,
retaining recorded_at (the sole mutation exception). Full review routing is slice 5.

POST `.../reassess` with `{"oracle":"<exact previous Oracle string>"}` requires execute.
Only current oracle_unavailable may be rechecked by the same frozen Oracle; no subject
call occurs. Response is a new Result with resolves. Failed re-attempts also become
new unavailable Results in a linear chain. Actionable/inconclusive retries or changed
Oracle are 409; control requalification conditions remain slice 5.

All decision collection reads support offset/limit (0/100 defaults; limit 1–1000) and
read permission. Generated fields/unknown request keys are rejected with 422. Not found
is 404, invalid state/scope/history conflict 409, missing atomic permission/wrong actor
kind 403. Baseline/override/policy/release actions generate Approval and Audit records.
Runtime/decision history survives live Project deletion with retain_history=true.
Use the Minimal Engine as one application process; its configuration/decision lock
serializes scoped Snapshot checks, configuration writes and decision recording.

## Slice 2 execution API

Configure provider URLs before startup as specified in [PROVIDERS.md](PROVIDERS.md).
`POST /projects/{project}/executions` requires `execute` and exactly
`{"suite":"suite-name","environment":"environment-name"}`. It synchronously returns
201 with `execution_batch_id` and `executions`, including failed executions as recorded
infrastructure failures rather than quality verdicts. Preflight errors return 404 for
missing resources or 422 for invalid settings, missing Variables, invalid fixed Evidence,
or unmapped model identifiers. Error bodies use `detail` naming the reason.

Authenticated `read` endpoints:
- `GET /projects/{project}/executions`: list with offset (default 0), limit (default
  100, range 1–1000), optional suite/environment/status and date_from/date_to filters.
  Date filters are inclusive ISO timestamps with timezone.
- `GET .../executions/{id}`: persisted metadata and frozen runtime configuration.
- `GET .../executions/{id}/conversation`: one completed transcript, or 409 if none.
- `GET .../executions/{id}/artifacts`: list with the same offset/limit convention.
- `GET .../executions/{id}/results`: immutable C.7 Results; optional oracle_type/verdict
  filters and the same offset/limit pagination.

Missing/invalid authentication returns 401, missing permission 403, missing Execution
404, invalid request fields 422. Finished records cannot be updated or deleted. Their
frozen configuration and Evidence remain readable even after live configuration deletion.

## Slice 3 assessment

Successful executions are automatically assessed before POST returns. All Constraints
run first, cheapest-first, and each produces a Result. Default AND and `hard-veto`
require all to pass; OR requires at least one. Any failed `veto: true` Constraint, or any
unavailable Constraint, prevents Judges from running. Empty Constraints pass vacuously.
Each Single Judge then produces one Result using the [HTTP contract](PROVIDERS.md).
Failed executions have no Results; skipped Judges have no fabricated Result.
Execution `completed` describes Evidence collection, independently of assessment quality.

Validators return verdict pass/fail, Confidence `not_applicable` and disposition actionable.
A broken/unsupported check or missing evidence produces oracle_unavailable with null
verdict, never fail/pass. Supporting evidence contains the frozen clause, selected
target, observed/expected facts and any error. Unnamed clause references are
`sha256:<frozen-contract-hash>/<constraints-or-expectations>/<zero-based-index>`;
declared ids are used directly. Oracle identity is canonical JSON with version/configuration.

Targets are deterministic dotted paths: `response` (last response), `conversation`
(full object), `conversation.turns.0.response`, `response.some_json_key`, `artifacts.*`
(all Artifact records), `artifacts.NAME` (matching data: scalar for one, list for several),
`artifacts.usage.0.total_tokens`, and `duration_ms` (recorded execution duration).
Missing paths are unavailable. A string is parsed as JSON when traversing into it.

Built-in expected formats:

| validator | target example | expected example / meaning |
|---|---|---|
| schema | response | JSON Schema object/Boolean applies to the target value as held in Evidence (Response is a string); `"json"` explicitly checks JSON syntax |
| forbidden-content | response | `{"patterns":["literal",{"regex":"(?i)unsafe"}]}`; pass iff none match |
| structural | conversation | `{"required_steps":["retrieve","answer"]}` or the list directly; substrings must occur in order in prompt/response transcript text |
| latency | duration_ms | `"500ms"` or numeric milliseconds; recorded duration <= maximum |
| cost | artifacts.usage | number (maximum total_tokens), or `{"metric":"cost","max":0.05}`; sum across target entries <= maximum |

Schema uses jsonschema 4.23.0, the schema's declared draft or the library default
(2020-12), with built-in format checks; only local fragment references are allowed.
No remote schema/resource retrieval occurs. JSON syntax is checked only by `expected:
"json"` or decoded during traversal into a JSON-bearing text target (`response.some_key`).
For example `{type: string, minLength: 1}` accepts a nonempty plain-text Response; an
object schema does not implicitly decode that Response. Malformed JSON with `expected:
"json"` is a completed fail; a malformed/missing path is unavailable;
invalid schemas are unavailable. Patterns use Python regex syntax; strings are literal,
case-sensitive substrings. Nontext forbidden-content targets use canonical JSON text.
Structural matching is literal and case-sensitive, across newline-joined prompt/response
turns or list items. Numeric latency lists are summed. Missing usage/metrics are unavailable.
Tool-call/Boundary Validators require the excluded acting-tools capability; attempts to
apply them produce unavailable and block validation.

### Custom Validator registration

`POST /projects/{project}/validators` requires `contract_define` and the existing
Approval Workflow (Service Accounts need X-Approved-By and X-External-Review-Ref).
It returns 201; duplicate name/version returns 409. Invalid rules return 422.
`GET /projects/{project}/validators` requires read and supports offset/limit.
No modification/deletion endpoint or arbitrary executable loading is provided.

```json
{
  "name": "domain-status",
  "version": "1",
  "rule": {"operation":"equals","expected":"approved"}
}
```

The complete rule language is:
- `{"operation":"equals","expected":<any JSON>}`: canonical JSON equality (true differs from 1).
- `{"operation":"range","minimum":0,"maximum":10}`: inclusive finite numeric bounds.
- `{"operation":"schema","expected":<schema or "json">}`.
- `{"operation":"forbidden-content","expected":{"patterns":[...]}}`.
- `{"operation":"structural","expected":{"required_steps":[...]}}`.

Unknown fields/operations, invalid rules, or built-in name shadowing are rejected.
Names/versions use letters, numbers, underscore, dot or hyphen. A Constraint uses:

```json
{"validator":"domain-status@1","target":"response.status","expected":null,"dimension":"functional"}
```

Custom Constraints require explicit dimension. Their expected accepts **null or {}**
for these parameterless checks, because the immutable registered rule defines the
expectation. All other structures are rejected at configuration load (422), naming the
clause by id or by validator/target if unnamed (owner decision O-2, intended A.5 0.41.2).
Bare name binds only when exactly one version exists.
Missing/ambiguous registration is unavailable. Definitions are frozen before execution.
The evaluator receives only selected Evidence and its frozen rule, with no clock,
randomness, network, filesystem, imports or user code. This declarative registration
implements Volume V's Custom Validator interface without a plugin or language SDK.

### Admission

`POST /projects/{project}/admissions` requires a **Person** with `review` permission.
`GET /projects/{project}/admissions` requires read, supports offset/limit and optional
oracle filter, and lists records in acceptance order, oldest first. Example POST:

```json
{
  "oracle":"<exact Judge Result oracle string>",
  "reference_set":"reference@1",
  "items":10,
  "verdict_distribution":{"pass":7,"fail":3},
  "raw_agreement":0.8,
  "measure":"cohen_kappa",
  "chance_corrected_agreement":0.7,
  "threshold":0.7,
  "admitted":true,
  "labelled_by":["reviewer-person-id"],
  "arbitrations":[]
}
```

All fields except arbitrations are required. The engine generates id, recorded_at and
recorded_by; supplying any of them is rejected (422), as are unknown keys. Counts must
be nonnegative integers summing to positive integer items, with only pass/fail keys.
raw_agreement must be [0,1]. Chance agreement and threshold are finite numbers for the
Project's named measure; admitted must exactly equal chance agreement >= threshold.
`"not_computed"` is allowed for chance agreement only with admitted false. No nulls,
numeric strings or Boolean substitutes for numbers are accepted. labelled_by must name
at least one existing Person. An absent arbitrations field is preserved as absent;
empty means there was no disagreement. Admission is append-only; no PUT/PATCH/DELETE.
The last accepted record for the exact Oracle determines admission and may withdraw it.
It does not suppress diagnostic Judge calls; admission-dependent Gates belong to slice 4.

The API records supplied agreement evidence; it does not invent reviewer independence
or automatically score a Reference Set. Reviewers should be independent of Judge tuners,
label items blind, exclude alignment/exposed items, record arbitration reasoning, draw
from multiple sources and version their Reference Set (Volume VI Admission SHOULDs).

## Running the Engine

The engine is built on Python 3.12, FastAPI, SQLite, and Uvicorn.

### Local Installation & Startup

```bash
# Create virtual environment (optional)
python -m venv .venv
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn engine.main:app --host 127.0.0.1 --port 8000
```

## Authentication & Authorization

All requests to the REST API must include a valid Bearer token in the `Authorization` header:

```http
Authorization: Bearer <principal-token>
```

### Principals, Teams, Roles, and Permissions

Governance (Volume XII; Appendix C §C.4) requires every request to resolve to a Principal (a `person` or a `service_account`).

- **Bootstrap / Admin Token**: The engine provides a pre-configured or environment-configurable admin token (e.g. `AQEF_ADMIN_TOKEN` or default bootstrap token `admin-token`) associated with an administrative Person principal possessing all permissions (`admin`, `read`, `project_create`, `project_edit`, `project_delete`, `environment_create`, `environment_edit`, `environment_delete`, `suite_create`, `scenario_create`, `scenario_edit`, `scenario_delete`, `contract_define`, `dataset_create`, `team_admin`, `role_admin`, `audit_read`, etc.).
- **Creating Teams**:
  - `POST /teams` with payload `{"id": "qa-team", "name": "QA Engineering", "description": "Testing team"}`. Requires `team_admin`.
- **Creating Roles**:
  - `POST /roles` with payload `{"name": "contract_author", "permissions": ["read", "contract_define"]}`. Requires `role_admin`.
- **Managing Principals**:
  - Administrative endpoints or seeding allows creating Person and Service Account principals. A Service Account must always specify `owner_person_id`.

## HTTP Status Codes

The engine returns standard HTTP status codes consistently:

| Status Code | Reason / Meaning |
|---|---|
| **200 OK** | Successful read, update, or action execution |
| **201 Created** | Successful resource creation |
| **204 No Content** | Successful deletion |
| **400 Bad Request** | Malformed JSON or invalid syntax |
| **401 Unauthorized** | Missing or invalid Bearer token |
| **403 Forbidden** | Caller lacks the required Permission for this operation |
| **404 Not Found** | Resource or parent resource not found |
| **409 Conflict** | Name uniqueness violation, duplicate immutable dataset version, composition conflict, or deletion referential integrity violation |
| **422 Unprocessable Entity** | Semantic validation rule failure (e.g. invalid template variables, empty contract, mutual exclusivity violation) |
