# HTTP provider interface — slices 2–5

## Startup mapping

At application construction (`engine.main.create_app`, including the module-level app
loaded by uvicorn), read `AQEF_PROVIDER_URLS` once: a JSON object mapping exact,
case-sensitive model identifiers to complete HTTP(S) POST URLs. No suffix is appended.
No URL belongs in AQEF configuration. Changes require a restart. Empty/unset mapping
allows definition-only work; an unmapped subject rejects execution preflight with 422,
before any call or batch insertion. Malformed settings fail application construction.
URLs must have a hostname, no credentials or fragment, and use http or https.

PowerShell, Python 3.12, from the project directory:

```powershell
$env:AQEF_PROVIDER_URLS = '{"subject-v1":"http://127.0.0.1:9001/subject","judge-v1":"http://127.0.0.1:9002/judge"}'
$env:AQEF_DB_PATH = 'aqef.db'
$env:AQEF_ADMIN_TOKEN = 'replace-this-token'
python -m uvicorn engine.main:app --host 127.0.0.1 --port 8000
```

Environment `model_version: subject-v1` resolves to the first URL. Judge `model:
judge-v1` uses the same namespace and resolves to the second endpoint; the Judge
protocol is specified below. `infra_target` does not select the URL.
`prompt_version` identifies configuration; the literal opening prompt comes from
`Scenario.prompt.template`, without an implicit external prompt store.

## Subject request

One JSON POST per turn, Content-Type application/json. All keys below are present:

```json
{
  "model": "subject-v1",
  "prompt": "Hello Ada",
  "environment": {
    "name": "staging",
    "model_version": "subject-v1",
    "prompt_version": "p1",
    "tool_configuration": null,
    "action_boundary": null,
    "infra_target": "local"
  },
  "variables": {"name": "Ada"},
  "context": {"turns": []}
}
```

Environment is frozen, including nullable fields; Variables are the resolved row or
Scenario mapping, identical across turns. Context contains only prior turns of this
Execution, each `{prompt: string, response: string}`. No custom authorization headers,
redirect following, transport retries, temperature or max_tokens are added. Required
upstream authentication can be handled by a deployment proxy.

Opening prompt placeholders are `{{name}}` or `{{ name }}`, with alphanumeric/underscore
names. Strings substitute literally; other JSON values use compact sorted-key JSON,
Unicode preserved, lowercase booleans/null. Substitution is one pass. Missing Variables
reject the entire batch before execution starts.

## Subject response

Return 2xx and a JSON object. Minimal valid response: `{"response":"Hello!"}`.
Full example:

```json
{
  "response": "Hello!",
  "complete": true,
  "artifacts": {"log":"raw log", "retrieval":{"text":"passage"}},
  "usage": {"prompt_tokens":12,"completion_tokens":3,"total_tokens":15}
}
```

- `response`: required strict string, including an empty or unfavorable answer.
- `complete`: optional strict Boolean, defaults true. False causes a next turn with
  literal prompt `Continue.` and the full prior transcript in `context.turns`. No tools
  are invoked. Continuation and termination depend deterministically on the responses.
- `artifacts`: optional string-keyed JSON object, defaults `{}`. Values may be any JSON.
  Supply transient data with the turn that produced it. Each entry is captured as
  `{name, data, turn}`; turn numbers begin at 1.
- `usage`: optional JSON object, defaults `{}`. Keys are provider-defined; token keys
  above are recommended. Nonempty usage becomes an Artifact named `usage`.
- Unknown fields and explicit nulls for these fields are rejected. The engine measures
  each call's latency as Artifact `latency_ms`; provider latency is not accepted.
  Duplicate Artifact names across turns are preserved.

Measured latency Artifacts also include `attempt` (1-based attempt number), including
failed HTTP calls. Their `turn` identifies the attempted turn even if it returned no Response.

Non-2xx (including 429 and redirects), network errors, malformed JSON and invalid
response envelopes are infrastructure failures. Retry is allowed only before any
response string was received in the Execution. A response string in an invalid envelope
is preserved as a partial turn and prevents retry. Later-turn failures also prevent
retry. Failure never creates a quality verdict or Oracle Result.

A single timeout deadline covers all turns/retries, starting when a worker begins,
excluding pool wait. Default 30s. Positive decimal durations with ms/s/m/h are accepted.
Each HTTP call is bounded by the remaining time; expiration prevents further calls.
Stopping the local wait cannot undo work already received by a remote provider.

## Trigger and Evidence resources

POST `/projects/demo/executions`, bearer authentication, JSON:

```json
{"suite":"smoke","environment":"staging"}
```

Returns 201 after completion: `{execution_batch_id: string, executions: [Execution]}`.
Each Scenario expands to one Execution per pinned static Dataset row; fixed Variables
or fixed Evidence produce one. Empty datasets produce zero. Ordering follows Scenario
then row declaration order, also in parallel output. Defaults: sequential, one worker,
zero retries. Suite settings override Project defaults field by field; retry replaces
its entire object. Explicit null settings are rejected. `retry.max_attempts` counts
retries per A.9: 2 permits one initial call plus at most two retries before a Response.

Execution metadata records frozen Environment, Scenario, effective Contract, Variables,
settings, actor/time, scheduling reason/order, batch/row identity, attempts, retry_count,
start/completion timestamps, duration_ms and error. Status is queued, running, completed
or infrastructure_failure. Scheduling is persisted before calls. Runtime history is
stored separately from deletable live configuration.

GET `.../executions/{id}/conversation` returns:

```json
{"turns":[{"prompt":"Hello Ada","response":"Hello!"}]}
```

Failed runs return 409 there; diagnostic partial_turns and Artifacts remain in metadata,
never assessed. Fixed Evidence uses this same nonempty Conversation shape, copies its
artifacts map with turn null, retains source_execution, and invokes no subject.
Confirmation and invalidation are documented in the slice 5 API section.

GET `.../{id}/artifacts` returns a paginated list of `{name, data, turn}`.
GET `.../{id}/results` returns immutable Validator and Single Judge Results in slice 3.
All resources require authentication and atomic read/execute permission.

## Judge request (http-judge-v1)

After Validation passes, each Single Judge Expectation sends one JSON POST to the exact
URL mapped from `judge.model`. The startup setting is the same `AQEF_PROVIDER_URLS`
shown above, read once at app construction. No endpoint suffix, hidden prompt, generation
settings, redirects or custom authentication headers are added. All request fields:

```json
{
  "model": "judge-v1",
  "criteria": "The answer is factually correct.",
  "confidence_source": "self_rating",
  "evidence": {
    "conversation": {"turns":[{"prompt":"What is 2+2?","response":"4"}]},
    "artifacts": [{"name":"latency_ms","data":12.5,"turn":1,"attempt":1}]
  }
}
```

Criteria is the exact Contract clause text. Evidence is the entire frozen Conversation
and Artifacts list, in the same format the execution resources return. No subject call
is made during assessment. `confidence_source` is `self_rating` or `token_probability`.
For self_rating the provider must obtain the Judge's own explicit Confidence in the
verdict; for token_probability it must return the model's probability for that verdict.
Both are returned in the same numeric `confidence` field. The engine does not reinterpret
Confidence as importance, a quality score or a panel vote count. Single Judge with
`agreement` is rejected for Single Judge at execution preflight; panel handling is below.

## Judge response

Return 2xx with this JSON object (all four keys required; no extra keys):

```json
{
  "verdict": "pass",
  "confidence": 0.93,
  "explanation": "The response states the correct sum.",
  "assertions": 1
}
```

`verdict` is exactly `pass` or `fail`; `confidence` is a finite JSON number in [0,1],
never a string, Boolean or null. `explanation` is a string supporting the verdict.
`assertions` is an integer >=1: the provider explicitly declares the number of
independent assertions its assessment aggregates. The engine cannot infer that count
from free-form criteria. Count 1 is omitted from the resulting C.7 Result; a larger
count is copied to the Result's `assertions`. No `panel` field appears for Single Judge.

At or above the clause's confidence_threshold, the Result is `actionable`, including
a fail verdict. Below it, the verdict and Confidence are retained with `inconclusive`.
Human routing and Result resolution follow docs/API.md; no low score is retried.

An unavailable Judge includes an unmapped model, non-2xx (429 and redirects included),
connection/read failure, timeout, invalid JSON, wrong/missing fields, nonfinite/out-of-range
Confidence, invalid verdict, or invalid assertions. Result disposition is
`oracle_unavailable`, verdict null and Confidence `not_applicable`. Received JSON,
including any verdict in an invalid envelope, is retained in supporting_evidence;
no usable Confidence is invented. Results are never silently treated as passes.

Exactly one attempt is made per Expectation. It has the configured ExecutionConfig
timeout as a fresh assessment budget after subject completion (default 30s), independent
of the subject's runtime deadline. The permitted optional Oracle transport re-attempt
is not used. Attempts, times, error and raw provider JSON or explanation are recorded
in supporting_evidence. Neither successful nor unavailable Results can be overwritten.

The Result's `oracle` is a canonical compact sorted-key JSON string, for example:

```json
{"confidence_source":"self_rating","criteria":"The answer is factually correct.","model":"judge-v1","type":"judge","version":"http-judge-v1"}
```

That exact string identifies this Judge configuration in Admission records. Different
models, confidence sources, criteria or protocol versions have different identities;
thresholds consume Confidence and do not change the Oracle that produced it.

## Multi Judge calls — slice 5

There are **no new Judge request or response fields**. Each configured Judge receives
its own ordinary http-judge-v1 POST, with its own `model`, literal clause `criteria`,
`confidence_source` and the same frozen Evidence. Its exact model identifier resolves
through AQEF_PROVIDER_URLS at startup, independently of the other panel members:

```powershell
$env:AQEF_PROVIDER_URLS = '{"subject-v1":"http://localhost:9001/subject","judge-a":"http://localhost:9002/judge","judge-b":"http://localhost:9003/judge"}'
```

For purpose independence with judges a/b, one POST goes to :9002 and one to :9003,
in configuration order. For purpose stability with judge-a and samples 3, three POSTs
go to :9002 with identical request conditions. No member receives another member's
response, a hidden consensus prompt, an extra system instruction or a fabricated vote.
Responses retain the same required verdict/confidence/explanation/assertions fields.

Every member's full C.7-shaped Result, stable id, response/error and attempts are kept
in the panel Result's supporting_evidence.member_results. They may be referenced by
Requalification. The execution Results collection exposes the panel's clause Result;
members are nested evidence, not additional quality-aggregate contributions.

Voting uses actual counted verdicts and ceil(fraction*count); majority is strictly more
than half. Its Confidence is the minimum own Confidence among winner voters. A forced
fail on disagreement uses minimum member Confidence. confidence_weighted_mean combines
Boolean pass scores using member Confidence as weights, retains mean own Confidence,
and reports weighted_pass_score and agreement separately. min_agreement is optional;
absent means no extra agreement minimum. Agreement is never substituted for a member's
own Confidence. A member configured confidence_source agreement is asked for self_rating
on the wire; its configured identity is retained and panel agreement is a separate signal.

An unavailable member contributes no vote. When eligible membership meets quorum but
a member is unavailable, the panel is oracle_unavailable. A Seeded Control exclusion
below quorum yields not_assessed. panel always contains configured and counted; stability
counts samples. With no quorum declared, the full configured panel is required.

If a partial unavailable panel is reassessed, any member response carrying a genuine
verdict is retained; only members failing before a verdict may be called again. A
verdict inside malformed Confidence/protocol data also prevents that member's retry.
A Single Judge response containing such a verdict cannot be re-attempted through reassess.
Nothing asks again until a more favorable answer appears. Control outcomes follow a
same-Oracle unavailable recovery while preserving the original unavailable Result.

Human Review does not call a model provider. Direct Human clauses create an awaiting
Result; consensus disagreement routes to a separate Human Result resolving the panel.
Single Judge low Confidence remains explicitly reviewable through the review endpoint.
No subject is invoked for fixed controls, Human review, or re-assessment of stored Evidence.
