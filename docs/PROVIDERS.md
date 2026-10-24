# HTTP provider interface — slice 2

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
judge-v1` uses the same namespace; Judge invocation and its wire contract belong to
slice 3 and are not implemented by this slice. `infra_target` does not select the URL.
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
Confirmation and invalidation belong to slice 5.

GET `.../{id}/artifacts` returns a paginated list of `{name, data, turn}`.
GET `.../{id}/results` returns `[]` in slice 2. No Validators or Judges run.
All resources require authentication and atomic read/execute permission.
