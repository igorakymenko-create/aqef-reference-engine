# AQEF GitHub Actions

Use the composite Action as a step. Provision an AQEF Service Account with
`read` and `execute`, and put its bearer token in a GitHub secret.

```yaml
- uses: igorakymenko-create/aqef-reference-engine@slice-16
  id: aqef
  with:
    engine-url: ${{ vars.AQEF_URL }}
    token: ${{ secrets.AQEF_TOKEN }}
    project: checkout
    suite: smoke
    environment: staging
```

| Input | Meaning |
|---|---|
| `engine-url` | Required engine base URL reachable from the runner. |
| `token` | Required bearer token from a secret. Passed to the entry point through its environment. |
| `project`, `suite`, `environment` | Required AQEF scope. |
| `execution-batch` | Existing batch in that scope. Omit to trigger a new one. |
| `wait-timeout` | Positive finite seconds. Default 60. The budget starts at entry-point startup and covers engine calls, polling and optional release recording. |
| `poll-interval` | Positive finite seconds between polls. Default 2. |
| `release-policy` | Standing policy ID for optional Release Decision recording. |

Outputs are `execution-batch` and `outcome`. If the trigger did not return
a batch identifier, the batch output is empty. The GitHub step succeeds
for `pass` or `pass_with_override` and fails for `fail`. The summary lists
every returned GateResult by name with its blocking/advisory type, raw
status and override approval ID where present.

A failed advisory Gate is reported and does not block. A failed blocking
Gate with an override on its exact GateResult contributes an overridden
pass. Any other failed blocking Gate keeps the step failing. Multiple
overrides apply individually. GitHub uses the workflow's check status as
its native mechanism. Branch protection can require that check. AQEF
defines and evaluates all Gates on the engine side.

## Waiting and evaluation identity

The Action uses the SDK for the same REST operations exposed by
`aqef execution run`, `aqef gates check` and `aqef gate-evaluation get`.
A trigger currently returns a completed batch. For an existing batch
still executing, a scoped check returns HTTP 202 with `status: pending`.
The Action waits for an evaluation, then retains its ID. It polls that
specific evaluation and reads its recorded GateResults with current
overrides. An override from an earlier batch or another evaluation is
outside that read.

A failed blocking Gate without an override stays eligible for polling
until the deadline. This covers a Gate blocked on `awaiting_review` and
a completed failure that a Person could still override. The engine
handles any configured `review_timeout` and role escalation. The Action's
separate deadline also bounds reviews without that setting. Advisory
failures alone do not cause a wait. API and transport errors fail the
step.

If the engine reports changed evidence, the Action requests a conditional
refresh linked to its current evaluation. The engine may create a new
evaluation when Results, Admission or Seeded Controls change. It refuses
to refresh an evaluation with an override or stale scope. An override
observed on an unchanged evaluation is read back without a new Gate check.
Timeout leaves a failing step and the latest Gate summary available.

While the step is waiting, a reviewer can use `aqef snapshot list --project PROJECT`
and `aqef gate-evaluation get --project PROJECT --evaluation SNAPSHOT_ID` to
find the evaluation for the batch and the exact GateResult ID to override.

## Optional Release Decision

Provide `release-policy` and grant the Service Account `release_decide` if
the pipeline should record a release. A Person must have approved the
standing policy for the account and scope. On `pass`, the Action requests
a Report pinned to the exact evaluation and submits an `approved` Release
Decision referencing that Report, Snapshot and policy. The engine checks
the current state and policy. A rejection fails the step.
`pass_with_override` can unblock the GitHub step, and release recording
is skipped for that outcome.

## Example workflow

[`aqef-example.yml`](../.github/workflows/aqef-example.yml) runs on pull
requests and manual dispatch on an Ubuntu GitHub-hosted runner. It starts
a loopback engine, subject and Judge, loads a Project with the CLI and
provisions a disposable Service Account. It uses local test credentials
generated in the job.

For a real deployment, point `engine-url` at the engine reachable from the
runner and pass the Service Account token from GitHub Secrets. Configure
the target Project, Suite and Environment on that engine. Store Gate
definitions and thresholds in the AQEF configuration.
