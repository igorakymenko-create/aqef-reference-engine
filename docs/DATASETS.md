# Generated and Production Replay Datasets

Declare versions in the Project's `datasets` or register them through the
[Dataset API](API.md#slice-14--dataset-versions). An inline non-static
declaration omits `rows` or uses `rows: []`. Use a fresh version identifier
for each generation or capture. Bind a Scenario
to the stored rows by `name@version`. Deployments configure source URLs at engine
startup. Scenario Executions use the stored rows even if the source is unavailable.

An identical inline declaration reuses the stored version. A change to its
generator or capture configuration requires a new version. For a Project
load, replies are staged until the whole configuration can be validated and
written atomically. See [Project load and warning details](API.md#inline-dataset-declarations-and-generator-warnings).

## Generation

Set `AQEF_PROVIDER_URLS` to include the generator model alongside the normal
subject and Judge mappings. For example:

```json
{"generator-v1":"http://localhost:9100/generate"}
```

A Dataset with `source: generated` supplies `generator.model` and
`generator.instruction`. It may also supply an integer `generator.seed`.
The engine sends one HTTP POST to that model's URL using the same HTTP
transport as Judges. The JSON request is the `generator` object, including
`seed` only if supplied. The JSON response is an array of Rows or an object
with just a `rows` array. Each Row has a unique nonempty string `id` and
a `variables` object. The engine preserves every row and its order.
The version records the generator configuration and UTC `generated_at`.

Volume IV recommends an independent model. The engine accepts a generator
identifier equal to a Project subject identifier after case and whitespace
normalization. It records `independence: "same_identifier_as_subject"` with
the version and includes the finding in the creating response's
`X-AQEF-Warnings` header. Operators judge weight and family independence.
Identifiers and URLs alone do not establish it.

## Capture

Set `AQEF_CAPTURE_URLS` to a JSON map from production source identifiers
to trusted capture-service URLs, for example:

```json
{"support-logs":"https://capture.example.internal/conversations"}
```

The adapter can query a log store or serve controlled test data. The engine
POSTs the `capture` object to the configured URL:

```json
{"source":"support-logs","date_range":["2026-10-01","2026-10-31"],"sampling":"random","sample_size":1,"anonymization":true}
```

When using the CLI with YAML, quote the dates so they parse as JSON strings.
The adapter applies the inclusive calendar date range and the named sampling
strategy to its source. It returns exactly `sample_size` records. It should
return an HTTP error when it cannot honor the request.

```json
{"conversations":[{"id":"session-1","anonymized":true,"conversation":{"turns":[{"prompt":"Where is my order?","response":"Please give your order number."},{"prompt":"It is [order ID].","response":"It has shipped."}]}}]}
```

Use unique record IDs. Each Conversation has one or more `{prompt,response}`
turns. The engine stores one Row per record with the Conversation in
`variables.conversation` and records the capture configuration and UTC
`captured_at`. Omit `prompt` in a replay Scenario. The engine sends each
captured prompt verbatim and uses current subject replies to build context.
The number of captured prompts sets the turn count. The original responses
remain in the stored Row.

## Privacy policy

For `anonymization: true`, the configured adapter must anonymize the full
transcript and supply a safe record ID before it returns the record. Every
record must attest `anonymized: true`. The engine rejects absent or false
attestations and discards the entire reply. The deployment must trust the
adapter to implement its anonymization policy. The engine cannot verify
anonymization of arbitrary free text.

Raw capture is disabled by default. Deployments may set
`AQEF_CAPTURE_ALLOW_RAW` to a JSON array of configured source IDs when their
policy permits raw capture. A request with `anonymization: false` then requires
each record to report `anonymized: false`.

Grant the atomic Permission `production_replay_read` in addition to the usual
operation permissions. It is required to create a replay version, read its
rows, run a replay Scenario and access any route scoped to a Project with a
replay version. This also protects derived Evidence and Reports. The Project is
omitted from ordinary Project listings for Principals without the Permission.
The protection persists after deletion with retained history. Fresh bootstrap
administrators receive the explicit Permission. Existing Roles retain their
grants. On an existing installation, provision a Role and Principal with this
Permission before using Replay.

Deployments are responsible for approving the storage, capture adapter, and
subject and Judge endpoints that may receive replay prompts or derived Evidence.
Generation and capture each have a 30-second deadline and use one request.
