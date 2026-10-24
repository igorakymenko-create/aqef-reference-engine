# AQEF Engine API Documentation

This documents the implemented API, including known differences from the specification.
See [CONFORMANCE-STATEMENT.md](CONFORMANCE-STATEMENT.md) and the rule-level
[review](CONFORMANCE-REVIEW.md). Team scoping, schema coverage and the
synchronous trigger are known gaps; this document does not imply full Conformance.

## Slice 5 — Human Review, panels and Seeded Controls

The body of POST /executions still uses suite/environment. Optional
`"gates":["safety-gate"]` requests evaluation after assessment; names must apply to the
scope, and the response adds gate_evaluation (all applicable Gates are evaluated so a
caller cannot discard unfavorable Gates). Human pending Results remain blocking.

### Recording a Human Reviewer's verdict and Role routing

Direct Human Expectations bind `human_reviewer: {role: security-reviewer,
captures_confidence: false}`. They produce a C.7 Human Result with awaiting_review,
verdict null, confidence not_applicable and the declared review Role. Only a Person
with review permission and the routed Role may return a verdict. For an inconclusive
Judge without a named Human Role, review permission suffices. Example resolving that
Judge: POST `/projects/demo/executions/e-1/results/judge-result-1/review`:

```json
{"verdict":"pass","confidence":0.95,"supporting_evidence":{"reason":"Checked the cited primary source"}}
```

Response 201:

```json
{"id":"human-result-2","execution":"e-1","clause":"factual","resolves":"judge-result-1",
 "oracle_type":"human_reviewer","oracle":"{\"role\":\"review\",\"type\":\"human_reviewer\",\"version\":\"1\"}",
 "verdict":"pass","confidence":0.95,"disposition":"actionable",
 "supporting_evidence":{"reviewer":"alice","reviewed_at":"2026-10-24T12:00:00+00:00","evidence":{"reason":"Checked the cited primary source"}},
 "recorded_at":"2026-10-24T12:00:00+00:00"}
```

The original Judge Result is unchanged. The new Result is the effective chain tip.
Actionable/already-resolved Results cannot be reopened; invalidation requires a qualified
corrected Oracle rather than an ordinary review shortcut. A review never invokes subject.

### Completing an awaiting review

GET `/projects/demo/executions/e-1/results` shows routing information on pending Human
Results, for example:

```json
{"id":"human-pending-1","execution":"e-1","clause":"signoff","oracle_type":"human_reviewer",
 "oracle":"{\"role\":\"security-reviewer\",\"type\":\"human_reviewer\",\"version\":\"1\"}",
 "verdict":null,"confidence":"not_applicable","disposition":"awaiting_review",
 "supporting_evidence":{"review":{"role":"security-reviewer","captures_confidence":false,"timeout":"24h","on_timeout":"block","escalate_to":null},"criteria":"Security sign-off","evidence":{"conversation":{"turns":[{"prompt":"Question","response":"Answer"}]},"artifacts":[]}},
 "recorded_at":"2026-10-24T11:00:00+00:00",
 "review_route":{"role":"security-reviewer","state":"pending","captures_confidence":false,"timeout":"24h","required_roles":["security-reviewer"]}}
```

POST `/projects/demo/executions/e-1/results/human-pending-1/review`:

```json
{"verdict":"pass","supporting_evidence":{"reason":"Security inspection complete"}}
```

Response 201 keeps the same id and recorded_at:

```json
{"id":"human-pending-1","execution":"e-1","clause":"signoff","oracle_type":"human_reviewer",
 "oracle":"{\"role\":\"security-reviewer\",\"type\":\"human_reviewer\",\"version\":\"1\"}",
 "verdict":"pass","confidence":"not_applicable","disposition":"actionable",
 "supporting_evidence":{"review":{"role":"security-reviewer","captures_confidence":false,"timeout":"24h","on_timeout":"block","escalate_to":null},"criteria":"Security sign-off","evidence":{"reason":"Security inspection complete"},"reviewer":"alice","reviewed_at":"2026-10-24T12:00:00+00:00","reviewed_route":{"role":"security-reviewer","state":"pending","captures_confidence":false,"timeout":"24h"}},
 "recorded_at":"2026-10-24T11:00:00+00:00"}
```

This is the sole in-place Result mutation. Captured Confidence is numeric [0,1] and
required when captures_confidence is true; otherwise omit it, never send null. A direct
Human interface declaring captures_confidence false rejects a supplied numeric rating.
review_timeout defaults to 24h. Shorthand and ISO PT durations are supported. Expiration
is derived at read/review: block shows timed_out, still blocking; escalate routes to
escalate_to and shows escalated. The escalated Role replaces the original Role only
after expiration. Neither policy creates a verdict. Corrected Human Oracle routing
cannot waive the frozen clause's policy Role; required_roles lists all required Roles.

### Panel configuration, panel output and quorum

Example Expectation (the normal http-judge-v1 calls are detailed in PROVIDERS.md):

```json
{"id":"answer-quality","criteria":"The answer is correct.","confidence_threshold":0.7,
 "multi_judge":{"purpose":"independence","judges":[{"model":"judge-a","confidence_source":"self_rating"},{"model":"judge-b","confidence_source":"token_probability"}],
 "consensus":{"method":"voting","threshold":"majority","min_qualified":1,"on_disagreement":"human_review"}}}
```

Stability instead uses purpose stability, judge (one config) and samples >=2, with no
judges list. Consensus methods are voting/confidence_weighted_mean; unsupported methods
are rejected before execution. Voting accepts majority, unanimous or a number >0.5
and <=1. Panel Results returned in GET .../results include:

```json
{"id":"panel-result-1","execution":"e-1","clause":"answer-quality","oracle_type":"judge",
 "oracle":"<canonical panel configuration JSON>","verdict":"pass","confidence":0.9,"disposition":"actionable",
 "panel":{"configured":2,"counted":1},
 "supporting_evidence":{"purpose":"independence","member_results":[],"excluded_oracles":["<excluded Oracle>"],"quorum":1,"agreement":1.0},
 "recorded_at":"2026-10-24T12:00:00+00:00"}
```

The member_results list in an actual response contains every configured member/sample's
full Result, including stable id, own Confidence, raw provider response or error. The
empty list above is a shape illustration, not an omitted actual transcript. configured
is full membership; counted is actual verdicts after exclusions. With no declared quorum
all members are required. A missed member is excluded for affected classes; stability
excludes all its samples. Below quorum gives not_assessed. Unavailable members are never
votes. Unresolved consensus routes a new awaiting Human Result resolving the panel;
on_disagreement fail records a fail instead. Report signals.multi_judge records purpose;
low_confidence includes panel and member denominators, including 0 inconclusive cases.
Admission requires every configured member configuration, not an invented panel admission.

### Human confirmation of a Seeded Control

Fixed Evidence uses exactly the stored Execution Conversation form, not a chat-message
array. Example Scenario fragment:

```json
{"seeded_control":{"kind":"defect","defect_class":"toxicity","planted_defect":"unsafe phrase","confirmed_by":"construction"},
 "evidence":{"conversation":{"turns":[{"prompt":"Say hello","response":"unsafe phrase"}]},"artifacts":{},"source_execution":"earlier-execution-id"}}
```

`turns` must be nonempty; each turn requires string `prompt` and `response`, with no
extra fields. Invalid `evidence.conversation` is rejected at configuration load/change
with HTTP 422 and the field path in `detail[].loc`, including nested Project and Suite
loads and Scenario POST/PUT. The same model validates runtime Conversations.

Controls run before normal assessments. Construction uses fixed Evidence without calling
the subject; Validator confirmation checks actual captured Evidence against confirmation;
Human confirmation stays invalid until a Person with review records the fact. Example:
POST `/projects/demo/executions/e-1/seeded-controls/toxicity-control/confirm`:

```json
{"confirmed":true,"supporting_evidence":{"reason":"Verified the planted phrase in the captured response"}}
```

Response 201 has the C.3 control fields (additional IDs/provenance/per-Oracle trace fields
are also returned):

```json
{"scenario":"toxicity-control","defect_class":"toxicity","kind":"defect","outcome":"missed",
 "confirmed_by":"human_reviewer","invalidation_scope":"defect_class","reason":null}
```

For a clean control this confirms absence of the class; outcomes are passed/false_alarm.
Until Evidence is confirmed the control is invalid, never a catch/miss. A control awaiting
its Oracle's actual verdict also remains invalid rather than inventing a verdict.
The endpoint may use any Execution of that same batch. It requires a Person, rejects
duplicate/negative/empty-Evidence confirmations, and does not fabricate a quality verdict.
A zero reference-Oracle prior also requires this Human sanity check, including for fixed
construction controls. Clean controls carry no difficulty prior. Numeric priors require
basis/source; exact-model nonindependent references are rejected. Priors never update
from tested Oracle performance. Blind review, generator diversity, tuner separation and
recent same-Environment source_execution are authoring SHOULDs; this API has no UI that
can guarantee blindness or infer undeclared provenance.

### Where seeded_control_results appears

POST /executions and GET `/executions/{execution}` include seeded_control_results whenever
the batch has controls: one entry per control Scenario, also on ordinary Executions.
Each entry has the required fields shown above plus per-Oracle outcomes, tested Result
IDs, confirmation evidence, batch identity and difficulty_prior where applicable.
Only same-Oracle Results sharing the class are invalidated; undeclared/empty classes
cover all tested classes. An actual miss takes precedence in a multi-Oracle summary;
per-Oracle details remain authoritative. All dataset rows must confirm the declaration.

GET .../results derives, without storing on the original Result:

```json
{"invalidated_by":[{"scenario":"toxicity-control","defect_class":"toxicity"}]}
```

This is an added read-only field on the full Result. Original verdict/disposition are
unchanged. A later affected assessment is not_assessed, with no Oracle call. Other Oracles
and classes continue. Controls never enter quality aggregates/Basis. Confirmations can
arrive later and change current Gate evaluation; frozen Reports/GateResults/Releases stand.

### Full-run invalidation

POST `/projects/demo/executions/e-1/seeded-controls/toxicity-control/invalidate`, permission
seeded_control_invalidate (an ordinary checked, logged action, no Approval Workflow):

```json
{"reason":"The instrument failure compromises this entire candidate run"}
```

Response 201, required control fields:

```json
{"scenario":"toxicity-control","defect_class":"toxicity","kind":"defect","outcome":"missed",
 "confirmed_by":"construction","invalidation_scope":"full_run","reason":"The instrument failure compromises this entire candidate run"}
```

The control must actually be missed/false_alarm; a reason is mandatory. Service Accounts
may invoke this action with the permission. Under on_seeded_control_miss halt_run, scope
is automatically full_run and reason is exactly halt_run. Subsequent unstarted Executions
are cancelled without subject/Oracle calls. Every original Result in the run is blocked,
including other Oracles/classes. Gates use seeded_control_miss or seeded_control_false_alarm,
not a fictitious product-quality failure. Default skip_class affects only the failed class.

### Record Requalification and reassess stored Evidence

POST `/projects/demo/requalifications`, execute:

```json
{"oracle":"<exact corrected Oracle JSON from a fresh control Result>","defect_class":"toxicity",
 "controls":["fresh-defect-result","fresh-clean-result"],"diagnosis":"Corrected the Judge model configuration"}
```

Response 201:

```json
{"id":"qualification-1","oracle":"<exact corrected Oracle JSON from a fresh control Result>","defect_class":"toxicity",
 "controls":["fresh-defect-result","fresh-clean-result"],"diagnosis":"Corrected the Judge model configuration",
 "recorded_at":"2026-10-24T12:30:00+00:00","recorded_by":"operator"}
```

GET /requalifications is paginated with read permission. Generated fields are rejected
in input. Every control ID must be of the stated class and confirmed caught/passed by
that exact Oracle. Member IDs inside panel supporting_evidence may be used. Reused
Scenario/source_execution or identical captured Conversation exposed by a miss cannot
qualify. Control scores must follow the diagnosed/confirmed miss; prospective records
cannot authorize future misses. A false alarm requires fresh clean passes, a defect miss
fresh defect catches; both require both kinds, for every affected class.

POST `/projects/demo/executions/e-1/results/invalid-result-1/reassess`:

```json
{"oracle":"<exact corrected Oracle JSON from qualification-1>"}
```

Response 201 is a new full C.7 Result, for example:

```json
{"id":"corrected-result-1","execution":"e-1","clause":"toxicity","resolves":"invalid-result-1",
 "oracle_type":"judge","oracle":"<exact corrected Oracle JSON from qualification-1>","verdict":"pass","confidence":0.95,"disposition":"actionable",
 "supporting_evidence":{"criteria":"No toxic language.","evidence":{"conversation":{"turns":[{"prompt":"Question","response":"Answer"}]},"artifacts":[]},"attempts":[{"number":1,"started_at":"2026-10-24T12:31:00+00:00","completed_at":"2026-10-24T12:31:01+00:00"}],"provider_response":{"verdict":"pass","confidence":0.95,"explanation":"Checked content","assertions":1},"explanation":"Checked content","requalified_controls":["batch-1:smoke/toxicity-control"]},
 "recorded_at":"2026-10-24T12:31:00+00:00"}
```

The subject is not called. The old Result is untouched; re-evaluation may read the new
effective Result. Same Oracle is allowed only for uninvalidated oracle_unavailable and
only before a genuine verdict was received. Partial panel recovery retains every member
verdict already returned and calls only members that failed before any verdict. Corrected
configuration cannot weaken frozen criteria/target/expected or panel purpose/count/
Consensus/quorum. A corrected Human Role also retains the original clause's policy Role
unless its configured escalation applies. An actionable effective Result is never reopened.

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
where a Gate does not require Admission. Panel/control reporting is described above.
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
retaining recorded_at (the sole mutation exception). Full review routing is described above.

POST `.../reassess` with `{"oracle":"<exact previous Oracle string>"}` requires execute.
Only current oracle_unavailable may be rechecked by the same frozen Oracle; no subject
call occurs. Response is a new Result with resolves. Failed re-attempts also become
new unavailable Results in a linear chain. Actionable/inconclusive retries or changed
Oracle are 409 unless the corrected Oracle satisfies the slice 5 requalification conditions above.

All decision collection reads support offset/limit (0/100 defaults; limit 1–1000) and
read permission. Generated fields/unknown request keys are rejected with 422. Not found
is 404, invalid state/scope/history conflict 409, missing atomic permission/wrong actor
kind 403. Baseline/override/policy/release actions generate Approval and Audit records.
Runtime/decision history survives live Project deletion with retain_history=true.
Use the Minimal Engine as one application process; its configuration/decision lock
serializes scoped Snapshot checks, configuration writes and decision recording.

## Slice 2 execution API

Configure provider URLs before startup as specified in [PROVIDERS.md](PROVIDERS.md).
`POST /projects/{project}/executions` requires `execute` and
`{"suite":"suite-name","environment":"environment-name"}`, with optional `gates`
as described above. It synchronously returns
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

### Audit and retained history (D-6, XII Principals/Audit; C.8)

Every successful permission-checked HTTP action, including reads, records the actor's
`principal_id`, `principal_kind`, atomic permission as `action`, timestamp and
`details.target`/`details.method`. Existing governed-action records retain their Approval
link and specific target; the same permission is not logged twice for that request.
Failed requests do not produce a successful-action record. Human Review/confirmation/
invalidation are included. Audit reads are recorded after constructing their response,
so the current read appears on the next query. Global operations use audit project
`__global__`, readable through `/projects/__global__/audit` with `audit_read`.

Each new Execution additionally stores top-level `principal_id` and `principal_kind`
for its trigger; scheduling.requested_by is preserved. These fields do not retroactively
invent an actor kind for an older Execution.

`DELETE /projects/p?retain_history=true` removes live configuration and records
`details.deletion_kind: configuration_only_history_retained` and `retain_history: true`.
Without that option the requested kind is `configuration_and_history`, and deletion
is rejected if protected history exists: no separate history-purge API is offered.
Subresource deletions retain runtime history and record the configuration-only kind.
Creation itself is audited, so an API-created Project normally needs explicit retention.

After deletion, `GET /projects/p` is 404, but historical URLs still work with their
normal permissions:

```http
GET /projects/p/audit?action=project_delete
Authorization: Bearer <auditor-token>
```

Response 200 is a paginated array of AuditLogEntry objects, including the deletion
actor/kind and requested deletion kind. `/projects/p/approvals`, `/projects/p/executions`,
`/projects/p/executions/{id}` and its conversation/artifacts/results subresources, and
saved reports/snapshots/baselines/releases/release-policies remain readable. Access
still requires audit_read for audit/approvals or read for runtime/decision history;
live Project existence is not required for those retained records.

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
  - `POST /principals` requires `role_admin`, returns 201 and accepts `id`, `kind`
    (`person`/`service_account`), `name`, optional `email`, `team_ids` (default []),
    `roles` (default []), `owner_person_id`, and `token`. A Service Account's owner must
    resolve to an existing Person (422 otherwise); Person cannot have an owner.
    Omitted/empty token falls back to the Principal id. Token is not returned.
    Role/Team name references are stored as supplied; Team membership does not yet
    restrict Project access (review G1). Tokens/Principal ids must be unique (409).
    Principal/Team/Role DTOs currently ignore extra input keys, unlike strict AQEF
    configuration DTOs. Admin Role name/permission grants wildcard permissions; actor
    kind, Human Role, policy and currency checks still apply.

## HTTP Status Codes

The engine returns standard HTTP status codes consistently:

| Status Code | Reason / Meaning |
|---|---|
| **200 OK** | Successful read, update, or action execution |
| **201 Created** | Successful resource creation |
| **204 No Content** | Successful deletion |
| **400 Bad Request** | Resource name in a replacement/version body does not match its path |
| **401 Unauthorized** | Missing or invalid Bearer token |
| **403 Forbidden** | Caller lacks the required Permission for this operation |
| **404 Not Found** | Resource or parent resource not found |
| **409 Conflict** | Name uniqueness violation, duplicate immutable dataset version, composition conflict, or deletion referential integrity violation |
| **422 Unprocessable Entity** | Malformed JSON, request/model validation or semantic validation failure (field paths for model errors, a reason string for explicit checks) |

All collection endpoints, including configuration and governance lists, use the same
offset/limit convention: offset defaults to 0, limit to 100, limit range 1–1000.
Unknown query parameters are ignored. Array order follows storage insertion order
for runtime/decision history; configuration ordering is the storage's stable order.
Audit supports action and principal_id filters only; no date/Team filter. Dataset GET
and rows accept optional version; omitted version uses latest registration. Query
parameters for every operation are in the code-derived inventory artifact below.

`AQEF_ADMIN_TOKEN` is consumed only when creating the initial admin Principal in a
database; changing it later does not rotate an already stored token. Generated
response configuration includes defaulted/null fields rather than necessarily echoing
only supplied fields. Most AQEF configuration models reject unknown keys; governance
models are the exception described above. A 422 reason is not guaranteed to be a string:
request errors use FastAPI's field-path list.

## Dynamic runtime response contracts

The runtime examples above show representative values. These are the complete top-level
field families used by responses whose OpenAPI output schema is unconstrained:

| Response | Fields and conditions |
|---|---|
| Execution batch (POST) | `execution_batch_id` string, `executions` array of Execution metadata; optional `gate_evaluation` when `gates` was supplied. |
| Execution metadata | `id`, `execution_batch_id`, `project`, `suite`, `scenario`, `environment`; nullable `dataset`/`row_id`; `variables` map; `configuration` with environment/scenario/effective contract/validators/defect_classes/execution settings; `scheduling` with strategy/order/reason/requested_by/requested_at; `status`; created_at/started_at/completed_at (latter two nullable); attempts array; retry_count; conversation nullable; partial_turns array; artifacts array; error nullable; opening_prompt nullable. `duration_ms` exists after worker collection. Fixed Evidence adds nullable source_execution. A batch containing controls adds seeded_control_results to each metadata response. |
| Attempt | number, started_at, completed_at after completion, nullable error. Artifacts are name/data/turn; measured latency also has attempt. Failed/partial subject text stays in partial_turns. |
| Result | id/execution/clause/oracle_type/oracle, verdict (pass/fail or null), confidence (finite number or not_applicable), disposition, supporting_evidence map, recorded_at. Optional resolves, panel, assertions are omitted when absent, never emitted as null. Derived invalidated_by appears only when applicable; review_route appears for pending Human Results and contains role, state, required_roles, captures_confidence and timeout duration. Policy and escalate_to remain in supporting_evidence.review. |
| Gate evaluation | id, snapshot_id, execution_batch_id, gates map, result_ids, evaluated_at, result_state digest, admissions map and control_state digest. Each GateResult has id/status/blocking/threshold/value/basis; fail includes reasons; an overridden copy includes override Approval id; ThresholdMap adds metric_basis. |
| Snapshot | id, captured_at, project, suites, environments map, contracts content-version map, inline_contracts map, quality_gates list; additionally contract_contents, effective_contracts and seeded_scenarios preserve scope reconstruction. baselines is a list of ids; release_label is optional. |
| Report | id, generated_at, scope (project/suites/environments/execution_batch_ids), snapshot_id, gates, metrics list, signals with all six lists. Metrics have name/definition/value/result_ids; regression comparison adds baseline_id and possible_causes. |
| Baseline | id, suite, scenario, environment, execution_id, result_id, frozen result/configuration/dataset/evidence, approval_id, approved_by/approved_at/approval_role; name optional. Evidence contains conversation and artifacts. |
| Override record | id (GateResult id), gate, execution_batch_id, justification, approval_id and approved_by/approved_at/approval_role. It does not change stored GateResult.status. |
| Release Policy | id/project/suites/environments/service_accounts, approval_id and approved_by/approved_at/approval_role. Revoked reads add revoked_by/revoked_at; original policy record remains unchanged. |
| Release Decision | id/project/suite/environment/execution_batch_id, report_id/snapshot_id, decision, gates, approval_id and approved_by/approved_at/approval_role; optional release_policy and notes. |
| Admission / Custom Validator | Admission request fields plus generated id/recorded_at/recorded_by; absent arbitrations remains absent. Custom Validator returns name/version/rule unchanged. |
| Requalification | id, oracle, defect_class, controls (Result ids), recorded_at, recorded_by; optional diagnosis. |
| Seeded Control entry (including confirm/invalidate responses) | id/execution_batch_id/suite/scenario/defect_class/kind/confirmed_by/confirmed; assessments and root_assessments Result-id lists; confirmation_details; policy, needs_reference_review, nullable source_execution; recorded_at/evidence_fingerprint; oracles list of oracle/outcome/result_ids; outcome/invalidation_scope/reason. Defect controls add difficulty_prior; actual misses add miss_recorded_at; Human confirmation adds confirmation_record (id/confirmed_by Person/recorded_at/supporting_evidence). |

Date/time fields are ISO strings with timezone. `value` may be numeric, a metric map,
or `not_computed`; threshold-map values can independently be `not_computed`. Supporting
evidence is type-dependent diagnostic data, not another accepted request contract.
Stored records are append-only except pending Human completion; response decoration
does not overwrite historical Results. Collection reads return arrays of the same
objects, with no envelope or total-count field.

<!-- CODE_DERIVED_OPERATIONS -->
## Registered operation inventory (slice 6)

This inventory is generated from the registered FastAPI operations. Exact typed request bodies, query/header parameters, defaults and response-model properties are in [OPENAPI.json](OPENAPI.json). Dynamic runtime response dictionaries have unconstrained OpenAPI schemas; use the execution, assessment and decision shapes/examples above. This is a documented schema gap (G3), not a promise that `{}` describes their fields.

Create status is listed per operation; all GET/PUT actions below return 200 unless an error occurs. HTTP errors use `{"detail": "reason"}`; request-validation errors use `{"detail":[{"loc":["body","field"],"msg":"reason","type":"..."}]}` (additional diagnostic keys may be present).

| Method | Path | Success | Request / response contract |
|---|---|---|---|
| GET | `/teams` | 200 | no body → list of Team |
| POST | `/teams` | 201 | Team → Team |
| GET | `/roles` | 200 | no body → list of Role |
| POST | `/roles` | 201 | Role → Role |
| POST | `/principals` | 201 | PrincipalCreateRequest → Principal |
| GET | `/projects/{project}/audit` | 200 | no body → list of AuditLogEntry |
| GET | `/projects/{project}/approvals` | 200 | no body → list of ApprovalRecord |
| GET | `/projects` | 200 | no body → list of Project |
| POST | `/projects` | 201 | Project → Project |
| GET | `/projects/{project}` | 200 | no body → Project |
| PUT | `/projects/{project}` | 200 | Project → Project |
| DELETE | `/projects/{project}` | 204 | no body → no body |
| GET | `/projects/{project}/environments` | 200 | no body → list of Environment |
| POST | `/projects/{project}/environments` | 201 | Environment → Environment |
| GET | `/projects/{project}/environments/{env}` | 200 | no body → Environment |
| PUT | `/projects/{project}/environments/{env}` | 200 | Environment → Environment |
| DELETE | `/projects/{project}/environments/{env}` | 204 | no body → no body |
| GET | `/projects/{project}/suites` | 200 | no body → list of Suite |
| POST | `/projects/{project}/suites` | 201 | Suite → Suite |
| GET | `/projects/{project}/suites/{suite}` | 200 | no body → Suite |
| GET | `/projects/{project}/suites/{suite}/scenarios/{scenario}` | 200 | no body → Scenario |
| PUT | `/projects/{project}/suites/{suite}/scenarios/{scenario}` | 200 | Scenario → Scenario |
| DELETE | `/projects/{project}/suites/{suite}/scenarios/{scenario}` | 204 | no body → no body |
| POST | `/projects/{project}/suites/{suite}/scenarios` | 201 | Scenario → Scenario |
| GET | `/projects/{project}/contracts` | 200 | no body → list of Contract |
| POST | `/projects/{project}/contracts` | 201 | Contract → Contract |
| GET | `/projects/{project}/contracts/{contract}` | 200 | no body → Contract |
| PUT | `/projects/{project}/contracts/{contract}` | 200 | Contract → Contract |
| GET | `/projects/{project}/datasets` | 200 | no body → list of Dataset |
| POST | `/projects/{project}/datasets` | 201 | Dataset → Dataset |
| GET | `/projects/{project}/datasets/{dataset}` | 200 | no body → Dataset |
| GET | `/projects/{project}/datasets/{dataset}/rows` | 200 | no body → list of Row |
| POST | `/projects/{project}/datasets/{dataset}/versions` | 201 | Dataset → Dataset |
| GET | `/projects/{project}/gates` | 200 | no body → list of QualityGate |
| POST | `/projects/{project}/gates` | 201 | QualityGate → QualityGate |
| PUT | `/projects/{project}/gates/{gate}` | 200 | QualityGate → QualityGate |
| POST | `/projects/{project}/executions` | 201 | ExecutionRequest → dynamic JSON |
| GET | `/projects/{project}/executions` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/executions/{execution}` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/executions/{execution}/conversation` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/executions/{execution}/artifacts` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/executions/{execution}/results` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/admissions` | 201 | AdmissionRequest → dynamic JSON |
| GET | `/projects/{project}/admissions` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/validators` | 201 | CustomValidator → dynamic JSON |
| GET | `/projects/{project}/validators` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/gates/check` | 200 | BatchRequest → dynamic JSON |
| POST | `/projects/{project}/snapshots` | 201 | SnapshotRequest → dynamic JSON |
| GET | `/projects/{project}/snapshots` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/reports` | 201 | BatchRequest → dynamic JSON |
| GET | `/projects/{project}/reports` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/gates/{gate}/override` | 201 | OverrideRequest → dynamic JSON |
| POST | `/projects/{project}/baselines` | 201 | BaselineRequest → dynamic JSON |
| GET | `/projects/{project}/baselines` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/release-policies` | 201 | PolicyRequest → dynamic JSON |
| GET | `/projects/{project}/release-policies` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/release-policies/{policy}/revoke` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/releases` | 201 | ReleaseRequest → dynamic JSON |
| GET | `/projects/{project}/releases` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/executions/{execution}/results/{result}/review` | 201 | ReviewRequest → dynamic JSON |
| POST | `/projects/{project}/executions/{execution}/results/{result}/reassess` | 201 | ReassessRequest → dynamic JSON |
| GET | `/projects/{project}/snapshots/{key}` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/baselines/{key}` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/reports/{key}` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/releases/{key}` | 200 | no body → dynamic JSON |
| GET | `/projects/{project}/release-policies/{key}` | 200 | no body → dynamic JSON |
| POST | `/projects/{project}/executions/{execution}/seeded-controls/{scenario}/confirm` | 201 | ConfirmRequest → dynamic JSON |
| POST | `/projects/{project}/executions/{execution}/seeded-controls/{scenario}/invalidate` | 201 | InvalidateRequest → dynamic JSON |
| POST | `/projects/{project}/requalifications` | 201 | RequalificationRequest → dynamic JSON |
| GET | `/projects/{project}/requalifications` | 200 | no body → dynamic JSON |
| GET | `/healthz` | 200 | no body → dynamic JSON |

Framework `/docs`, `/docs/oauth2-redirect`, `/redoc` and `/openapi.json` also require a bearer token (401 without one). They are not Reference UI. `/healthz` returns `{"status":"ok","specification_version":"0.41.1"}` with authentication. To view browser documentation, the browser must supply the Authorization header; no login/cookie flow is provided.
