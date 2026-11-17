# External plugins

Volume XVI plugins run as HTTP services. Set `AQEF_PLUGIN_URLS` at startup
to a JSON object such as `{"validator":"http://127.0.0.1:9200/validator"}`.
Each registration names one exact URL from that map. Calls use JSON POST
without redirects or AQEF credentials. Each call requires that the registered
URL still be allowlisted. The engine runs no code from a registration.

## Registry and lifecycle

Use `POST /plugins` with `type`, `name`, `version`, `endpoint` and
`configuration`. The immutable name and version form `name@version`.
Listing and history use `GET /plugins` and `GET /plugins/{plugin}`.
`POST /plugins/{plugin}/deprecate` retires a version, preserving its registration
and all existing Results, Baselines, materialized Datasets and Metrics. New or
changed configurations cannot bind it. Existing assessment bindings become
`oracle_unavailable` if invoked. Stored Dataset rows remain usable by existing
Scenarios. Registry requests use atomic grants through ordinary Roles. Reads
require `read`, registration requires `plugin_register` and retirement
requires `plugin_admin`. On existing installations, a Person holding
`role_admin` can assign these explicit grants to an appropriate Role.

Validator registration calls the service twice with identical input. The probe
uses the Conversation `{"turns":[]}`, `expected: null` and `repeatability-probe`
as both identifiers. Both replies must validate and their complete JSON must
match, irrespective of object key order. The registry reports only the number
of runs and the match on that probe. A Validator is responsible for returning
the same Result on equal input throughout use.

## Validator and Judge protocol

For a Constraint, use `validator: plugin:name@version` and declare `dimension`
and `target`. Its five request fields are `evidence` (the selected target value),
`expected`, `configuration` (the exact registry object), `execution` and `clause`.
For a Judge use `judge.plugin: name@version` alongside `model` and
`confidence_source`. The Judge gets `criteria` in place of `expected`, and
`evidence` is `{conversation, artifacts}` like the built-in Judge input.

Return a C.7 Result containing `id`, `execution`, `clause`, `oracle_type`,
`oracle`, `verdict`, `confidence`, `disposition`, `supporting_evidence` and
`recorded_at` (timezone-bearing ISO 8601). `execution` and `clause` echo the
request and `oracle` equals `name@version`. Successful replies have verdict
`pass` or `fail`. Validators return `confidence: not_applicable` and
`disposition: actionable`. Judges return finite numeric Confidence in [0,1],
`actionable` or `inconclusive` and `supporting_evidence.criteria` equal to the
clause criteria. An optional Judge `assertions` is an integer of at least two.
The engine assigns the stored ID and timestamp and applies its Confidence
Model. Transport, timeout, JSON and validation failures record
`oracle_unavailable` with no verdict. The assessment timeout is the configured
Execution timeout. Registration, Dataset and Report requests use five seconds
per call.

Reply fields outside the supported Result fields have no effect. Their names
are recorded in `supporting_evidence.ignored_reply_fields`. The engine cannot
prevent an external service using credentials it obtained separately from
calling the API. Such calls use that Principal's ordinary permissions. Use a
Service Account with an owning Person for plugin automation and grant only the
API permissions it needs. Governed approvals remain subject to Approval Workflow.

## Dataset and Report protocol

A Dataset declaration or registration uses `source: plugin`,
`plugin: name@version`, and the usual Dataset `name` and `version`. Supply no
rows. The plugin receives `name`, `version`, `configuration` and optional
`base_dataset`. It returns `{"rows":[{"id":"row-1","variables":{"topic":"greeting"}}]}`.
The engine validates every row and persists it with the pinned source only on
successful materialization. Scenarios bind the Dataset as `name@version`.

`POST /projects/{project}/reports/metrics` takes `execution_batch_id` and
`plugin: name@version`. The plugin receives `results` (the stored C.7 Results
for the batch) and `configuration`. It must return `name`, `value` and a
nonempty `result_ids` list drawn from those Results. A Metric with missing or
out-of-scope links is rejected. The engine stores the plugin version, batch ID
and Result links. Read it back with `GET /projects/{project}/reports/metrics/{metric}`.

## Examples

Run `uvicorn providers:app --app-dir examples/plugins --port 9200` and allowlist
the `/validator`, `/judge`, `/dataset` and `/report` URLs. The two assessment
examples take `configuration.oracle` for the exact registration ID. To exercise
rejections, set the Validator's `mode` to `variable` for a probe mismatch,
or `malformed` for an invalid Result on real Evidence.
