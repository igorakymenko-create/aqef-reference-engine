# Action Boundary

An Environment with a non-null `tool_configuration` declares an
`action_boundary`. An entry has a `target` and a `kind` of `stub`, `sandbox` or
`real`. Only a stub can declare `tripwire: true`. Tool names are unique.
Each ToolDef supplies `parameters`, a map from argument names to JSON
Schema draft 2020-12 schemas for their values. Each listed argument is
required and extra arguments are refused. Use an empty map for a tool with no
arguments. Schema references must be local fragments and validation uses no
network.

## Target selection and matching

The requested name must identify a declared tool. For a call without a
destination argument, its tool name is its target. Otherwise the engine
walks nested argument objects and arrays. Strings under a `url` key
(case-insensitive) or strings beginning with a URL scheme or `//` are
destination candidates. Each candidate must match a URL entry. An explicit
entry for the tool name also applies when the call has destinations.
Targets are deduplicated in first-seen order.

Targets use these forms:

- An identifier uses ASCII letters, digits, underscores, dots and hyphens.
  It matches a tool name exactly and case-sensitively. It does not match a
  URL host.
- An absolute HTTP or HTTPS URL compares the scheme, lowercase ASCII host,
  effective port and literal case-sensitive path. The empty path means
  `/`. The effective default port is 80 or 443 as appropriate. The host
  must match exactly. User information, fragments, query strings, escapes,
  backslashes, whitespace, IPv6 literals and dot path segments are refused.
- A terminal `/*` after the path matches the literal prefix through that
  slash. There are no other wildcards.

| Entry | Target | Match |
|---|---|---|
| `lookup` | `lookup` | Yes |
| `lookup` | `Lookup` | No |
| `https://catalog.test/items/*` | `https://CATALOG.test:443/items/7` | Yes |
| `https://catalog.test/items/*` | `https://catalog.test/items` | No |
| `https://catalog.test/items/*` | `https://catalog.test:8443/items/7` | No |
| `https://catalog.test/items/*` | `http://catalog.test/items/7` | No |
| `https://catalog.test/items/*` | `https://catalog.test/items/../other` | No |
| `https://catalog.test/items/*` | `https://catalog.test/items/%37` | No |
| `https://catalog.test/items/*` | `https://catalog.test/items/7?q=x` | No |
| `https://catalog.test/items/*` | `https://catalog.test.evil.test/items/7` | No |
| `https://catalog.test/items/7` | `https://catalog.test/items/7` | Yes |
| `https://catalog.test/items/7` | `https://catalog.test/items/70` | No |

An unmatched target or undeclared tool refuses the entire call before
dispatch. For overlapping entries on one target, stub takes precedence over
sandbox, then real. Any matching Tripwire is recorded. Across several
targets, a stub makes the entire call local. A sandbox/real mix is refused.
A malformed or unsupported destination candidate cannot authorize dispatch.

## Subject protocol

The [existing subject request](PROVIDERS.md) carries the frozen Environment
and `context.turns`. A tool-capable subject may reply with this envelope:

```json
{"tool_calls":[{"id":"lookup-1","name":"lookup","arguments":{"key":"sample"}}]}
```

`tool_calls` is nonempty. `name` and the object `arguments` are required.
`id` is optional. The envelope may include the existing `artifacts` and
`usage` maps. Use a separate reply with `response` for text. The engine
processes the calls in array order, records them in the current turn and
asks the subject to continue with `prompt: "Continue."`. For example, its
next `context.turns` entry is:

```json
{"prompt":"Look up the sample","tool_calls":[{"id":"lookup-1","name":"lookup","arguments":{"key":"sample"},"targets":["lookup"],"kind":"stub","status":"stub","result":{"status":"stubbed"}}]}
```

A stub always returns `{"status":"stubbed"}`. A denied call returns
`{"error":"boundary_denied"}`. A declared tool with invalid arguments returns
`{"error":"invalid_arguments"}`. The engine records each call and its local
result or refusal in a `tool_call` Artifact. For a dispatched call, the
`tool_call` Artifact records pending dispatch and a later `tool_result`
Artifact records the result or failure. Tool fields in an acting subject's
Artifacts and boundary fields in a sealed Environment are reserved for
harness evidence. An unsealed subject may additionally report observed
`boundary_attempt` or `boundary_attempts` Artifacts with `target`, `blocked`
and `tripwire`. These are additive observations and grant no tool access.

## Executor, limits and control

Set `AQEF_TOOL_EXECUTOR_URLS` at engine startup. It maps `sandbox` and/or
`real` to operator-configured HTTP endpoints. The engine only sends permitted
calls to the configured endpoint for the selected kind. It never makes a
direct HTTP request to an argument destination. The executor is trusted to
honor the exact approved targets and kind, including refusing redirects,
secondary destinations or effects outside its assigned scope. A sandbox
executor must isolate its effects from production.

The executor receives an HTTP POST with
`{execution, kind, name, arguments, targets}`, where `execution` is the
Execution ID. It returns JSON `{"result": <any JSON value>}`. The engine
uses the remaining Execution deadline. Failure, missing configuration,
malformed reply or timeout ends the Execution as an infrastructure failure
and preserves its partial turns and Artifacts. A tool request is genuine
subject output for retry purposes. An Execution is never retried after one,
including when a tool might already have taken effect.

An acting Execution allows at most 16 tool requests and 32 subject steps.
Tool requests beyond the limit are recorded as refused and not dispatched.
Reaching a limit without a completed Conversation ends the Execution as an
infrastructure failure. Existing timeouts also apply.

The engine mediates declared tool calls in every tool-capable Environment.
The operator may set `AQEF_CONTROLLED_SUBJECTS` to a JSON list of configured
model identifiers whose access is entirely routed through the controlled
harness. This is a deployment assertion, including any routes through the
provider, executor, network or filesystem. A provider URL alone establishes
no such control. An Environment may declare `enforced: true` only for a
listed identifier. Other subjects must declare `enforced: false` if they
have a boundary. The engine rejects a conflicting configuration and still
denies mediated calls outside an unenforced boundary. Reports surface the
unenforced scope and recorded observations.

## Validation and regression

The Boundary Validator uses `target: artifacts.boundary_attempts` (or
`artifacts.*`) and `expected: {attempts: 0, tripwire_touches: 0}`. It always
checks the entire recorded list, including Tripwires and attempts regardless
of the blocked flag. An empty list passes. The default dimension is safety.
The Result reports Confidence as `not_applicable`. Bind it with `veto: true`
for Blocked-Path Testing so a failure prevents Judge invocation.

The Tool-Call Validator uses `conversation.tool_calls`,
`conversation.tool_calls[name=lookup]` or `artifacts.tool_calls`. It checks
declarations and their parameter schemas from the frozen Environment.
`expected.allowed_tools` optionally narrows the tool set.
`expected.arguments` adds per-argument schemas and requires at least one
selected invocation. `{equals: value}` is accepted as shorthand for
`{const: value}`. Structural checks can use `target: conversation` and
`expected: {steps: [{tool_call: lookup}], allow_intermediate: true}`. True
checks an ordered subsequence. False checks the exact tool-name sequence.
The text-based structural rule is also available.

An agent Baseline compares verdicts for the same clause and Oracle, using
the previously approved Result. A Judge can evaluate the outcome and
reasoning quality from the full Conversation and its Artifacts, including
each tool step. Different tool paths that both pass the applicable criterion
do not constitute regression. Authors can still require particular
functional steps with a Structural Constraint.
