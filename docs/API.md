# AQEF Engine API Documentation

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

Custom Constraints require explicit dimension. Their expected is null because the
immutable registered rule defines the expectation; a non-null value is unavailable
rather than silently ignored. Bare name binds only when exactly one version exists.
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
