# AQEF CLI

Install with `python -m pip install ./client`. Set `AQEF_URL` to the engine URL
and `AQEF_TOKEN` to the caller's bearer token. Use `--url` to override the URL
or `--token-file PATH` to read the token from a file. Global options work before
the resource or after the command. There is no token argument.

Each operation calls the SDK method in the table once. Each FILE is a YAML or JSON
request body. For example, `aqef project load project.yaml` sends the parsed file
directly to POST /projects. YAML may parse `version: 1.0` as a number. Quote it as
`version: "1.0"` when the API expects a string. The CLI preserves the parsed data.
Approval headers are available as `--x-approved-by` and `--x-external-review-ref`
where listed. Optional query arguments and headers are omitted unless supplied.

`aqef execution run --project demo --suite smoke --environment test --wait`
uses the engine's synchronous trigger. The initial POST waits for the finished
batch and returns its Executions, so this engine needs no polling or second request.
Use `--timeout SECONDS` to set the finite HTTP timeout, 60 seconds by default.
This bounds waiting for the engine's response. A timeout does not cancel the batch.

The default display pretty-prints returned data for reading. `--json` writes
successful response bytes directly to stdout, including an empty body for HTTP 204.
HTTP errors are written to stderr with the status and original body. The CLI
suppresses the configured bearer token if it appears in displayed output.

| Exit code | Meaning |
|---|---|
| 0 | API success. |
| 1 | A returned GateResult in a Gate check, Report, Release Decision or Execution's embedded gate evaluation has `blocking: true`, `status: fail` and no `override`. This also applies to their list responses where present. The CLI reads these fields as returned. |
| 2 | HTTP API error. |
| 3 | Transport error or timeout. |
| 64 | Usage error, including an unreadable or unparseable body file. |

An overridden Gate keeps its returned status and override identifier in JSON.
The human-readable display additionally labels it overridden.

<!-- operations -->

| Command | SDK method | HTTP call | Appendix C |
|---|---|---|---|
| `aqef admission list --project PROJECT [--offset VALUE] [--limit VALUE] [--oracle VALUE]` | `list_admissions` | `GET /projects/{project}/admissions` | C.3 |
| `aqef admission record --project PROJECT FILE` | `record_admission` | `POST /projects/{project}/admissions` | C.3 |
| `aqef approval list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_approvals` | `GET /projects/{project}/approvals` | C.3 |
| `aqef audit list --project PROJECT [--action VALUE] [--principal-id VALUE] [--offset VALUE] [--limit VALUE]` | `get_audit_log` | `GET /projects/{project}/audit` | C.3 |
| `aqef baseline approve --project PROJECT FILE` | `approve_baseline` | `POST /projects/{project}/baselines` | C.3 |
| `aqef baseline get --project PROJECT --key KEY` | `get_baseline` | `GET /projects/{project}/baselines/{key}` | C.3 |
| `aqef baseline list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_baselines` | `GET /projects/{project}/baselines` | C.3 |
| `aqef contract create --project PROJECT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `create_contract` | `POST /projects/{project}/contracts` | C.3 |
| `aqef contract get --project PROJECT --contract CONTRACT` | `get_contract` | `GET /projects/{project}/contracts/{contract}` | C.3 |
| `aqef contract list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_contracts` | `GET /projects/{project}/contracts` | C.3 |
| `aqef contract update --project PROJECT --contract CONTRACT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `update_contract` | `PUT /projects/{project}/contracts/{contract}` | C.3 |
| `aqef dataset create --project PROJECT FILE` | `create_dataset` | `POST /projects/{project}/datasets` | C.3 |
| `aqef dataset get --project PROJECT --dataset DATASET [--version VALUE]` | `get_dataset` | `GET /projects/{project}/datasets/{dataset}` | C.3 |
| `aqef dataset list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_datasets` | `GET /projects/{project}/datasets` | C.3 |
| `aqef dataset rows --project PROJECT --dataset DATASET [--version VALUE] [--offset VALUE] [--limit VALUE]` | `get_dataset_rows` | `GET /projects/{project}/datasets/{dataset}/rows` | C.3 |
| `aqef dataset version --project PROJECT --dataset DATASET FILE` | `create_dataset_version` | `POST /projects/{project}/datasets/{dataset}/versions` | C.3 |
| `aqef environment create --project PROJECT FILE` | `create_environment` | `POST /projects/{project}/environments` | C.3 |
| `aqef environment delete --project PROJECT --env ENV` | `delete_environment` | `DELETE /projects/{project}/environments/{env}` | C.3 |
| `aqef environment get --project PROJECT --env ENV` | `get_environment` | `GET /projects/{project}/environments/{env}` | C.3 |
| `aqef environment list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_environments` | `GET /projects/{project}/environments` | C.3 |
| `aqef environment update --project PROJECT --env ENV FILE` | `update_environment` | `PUT /projects/{project}/environments/{env}` | C.3 |
| `aqef execution artifacts --project PROJECT --execution EXECUTION [--offset VALUE] [--limit VALUE]` | `list_artifacts` | `GET /projects/{project}/executions/{execution}/artifacts` | C.3 |
| `aqef execution conversation --project PROJECT --execution EXECUTION` | `get_conversation` | `GET /projects/{project}/executions/{execution}/conversation` | C.3 |
| `aqef execution get --project PROJECT --execution EXECUTION` | `get_execution` | `GET /projects/{project}/executions/{execution}` | C.3 |
| `aqef execution list --project PROJECT [--offset VALUE] [--limit VALUE] [--suite VALUE] [--environment VALUE] [--status VALUE] [--date-from VALUE] [--date-to VALUE]` | `list_executions` | `GET /projects/{project}/executions` | Not in Appendix C |
| `aqef execution run --project PROJECT (FILE or --suite S --environment E) [--wait]` | `trigger_execution` | `POST /projects/{project}/executions` | C.3 |
| `aqef gate create --project PROJECT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `create_quality_gate` | `POST /projects/{project}/gates` | C.3 |
| `aqef gate list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_quality_gates` | `GET /projects/{project}/gates` | C.3 |
| `aqef gate override --project PROJECT --gate GATE FILE` | `override_gate` | `POST /projects/{project}/gates/{gate}/override` | C.3 |
| `aqef gate update --project PROJECT --gate GATE [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `update_quality_gate` | `PUT /projects/{project}/gates/{gate}` | C.3 |
| `aqef gates check --project PROJECT FILE` | `check_gates` | `POST /projects/{project}/gates/check` | C.3 |
| `aqef principal create FILE` | `create_principal` | `POST /principals` | Not in Appendix C |
| `aqef project delete --project PROJECT [--retain-history VALUE]` | `delete_project` | `DELETE /projects/{project}` | C.3, C.8 |
| `aqef project get --project PROJECT` | `get_project` | `GET /projects/{project}` | C.3 |
| `aqef project list [--offset VALUE] [--limit VALUE]` | `list_projects` | `GET /projects` | C.3 |
| `aqef project load [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `create_project` | `POST /projects` | C.3 |
| `aqef project update --project PROJECT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `update_project` | `PUT /projects/{project}` | C.3 |
| `aqef release get --project PROJECT --key KEY` | `get_release` | `GET /projects/{project}/releases/{key}` | Not in Appendix C |
| `aqef release list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_releases` | `GET /projects/{project}/releases` | C.3 |
| `aqef release record --project PROJECT FILE` | `record_release` | `POST /projects/{project}/releases` | C.3 |
| `aqef release-policy approve --project PROJECT FILE` | `approve_release_policy` | `POST /projects/{project}/release-policies` | C.3 |
| `aqef release-policy get --project PROJECT --key KEY` | `get_release_policy` | `GET /projects/{project}/release-policies/{key}` | C.3 |
| `aqef release-policy list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_release_policies` | `GET /projects/{project}/release-policies` | C.3 |
| `aqef release-policy revoke --project PROJECT --policy POLICY` | `revoke_release_policy` | `POST /projects/{project}/release-policies/{policy}/revoke` | C.3 |
| `aqef report generate --project PROJECT FILE` | `generate_report` | `POST /projects/{project}/reports` | Not in Appendix C |
| `aqef report get --project PROJECT --key KEY` | `get_report` | `GET /projects/{project}/reports/{key}` | C.3, C.10 |
| `aqef report list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_reports` | `GET /projects/{project}/reports` | C.3, C.10 |
| `aqef requalification list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_requalifications` | `GET /projects/{project}/requalifications` | C.3 |
| `aqef requalification record --project PROJECT FILE` | `record_requalification` | `POST /projects/{project}/requalifications` | C.3 |
| `aqef result list --project PROJECT --execution EXECUTION [--offset VALUE] [--limit VALUE] [--oracle-type VALUE] [--verdict VALUE]` | `list_results` | `GET /projects/{project}/executions/{execution}/results` | C.3 |
| `aqef result reassess --project PROJECT --execution EXECUTION --result RESULT FILE` | `reassess_result` | `POST /projects/{project}/executions/{execution}/results/{result}/reassess` | C.3, C.7 |
| `aqef result review --project PROJECT --execution EXECUTION --result RESULT FILE` | `review_result` | `POST /projects/{project}/executions/{execution}/results/{result}/review` | C.3, C.7 |
| `aqef role create FILE` | `create_role` | `POST /roles` | C.3 |
| `aqef role list [--offset VALUE] [--limit VALUE]` | `list_roles` | `GET /roles` | C.3 |
| `aqef scenario create --project PROJECT --suite SUITE [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `create_scenario` | `POST /projects/{project}/suites/{suite}/scenarios` | C.3 |
| `aqef scenario delete --project PROJECT --suite SUITE --scenario SCENARIO [--x-approved-by VALUE] [--x-external-review-ref VALUE]` | `delete_scenario` | `DELETE /projects/{project}/suites/{suite}/scenarios/{scenario}` | C.3 |
| `aqef scenario get --project PROJECT --suite SUITE --scenario SCENARIO` | `get_scenario` | `GET /projects/{project}/suites/{suite}/scenarios/{scenario}` | C.3 |
| `aqef scenario update --project PROJECT --suite SUITE --scenario SCENARIO [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `update_scenario` | `PUT /projects/{project}/suites/{suite}/scenarios/{scenario}` | C.3 |
| `aqef seeded-control confirm --project PROJECT --execution EXECUTION --scenario SCENARIO FILE` | `confirm_seeded_control` | `POST /projects/{project}/executions/{execution}/seeded-controls/{scenario}/confirm` | C.3 |
| `aqef seeded-control invalidate --project PROJECT --execution EXECUTION --scenario SCENARIO FILE` | `invalidate_seeded_control` | `POST /projects/{project}/executions/{execution}/seeded-controls/{scenario}/invalidate` | C.3 |
| `aqef snapshot capture --project PROJECT FILE` | `capture_snapshot` | `POST /projects/{project}/snapshots` | C.3 |
| `aqef snapshot get --project PROJECT --key KEY` | `get_snapshot` | `GET /projects/{project}/snapshots/{key}` | C.3 |
| `aqef snapshot list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_snapshots` | `GET /projects/{project}/snapshots` | C.3 |
| `aqef suite create --project PROJECT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `create_suite` | `POST /projects/{project}/suites` | C.3 |
| `aqef suite get --project PROJECT --suite SUITE` | `get_suite` | `GET /projects/{project}/suites/{suite}` | C.3 |
| `aqef suite list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_suites` | `GET /projects/{project}/suites` | C.3 |
| `aqef system health` | `health_check` | `GET /healthz` | Not in Appendix C |
| `aqef team create FILE` | `create_team` | `POST /teams` | C.3 |
| `aqef team list [--offset VALUE] [--limit VALUE]` | `list_teams` | `GET /teams` | C.3 |
| `aqef validator list --project PROJECT [--offset VALUE] [--limit VALUE]` | `list_validators` | `GET /projects/{project}/validators` | Not in Appendix C |
| `aqef validator register --project PROJECT [--x-approved-by VALUE] [--x-external-review-ref VALUE] FILE` | `register_validator` | `POST /projects/{project}/validators` | Not in Appendix C |

71 commands.

## Not in Appendix C

- `aqef execution list` wraps `GET /projects/{project}/executions`. Execution history and filters extend C.6.
- `aqef principal create` wraps `POST /principals`. Principal provisioning is implementation-defined in C.4.
- `aqef release get` wraps `GET /projects/{project}/releases/{key}`. Direct lookup of an immutable C.3 Release Decision.
- `aqef report generate` wraps `POST /projects/{project}/reports`. Explicit freeze operation for the C.10 Report shape.
- `aqef system health` wraps `GET /healthz`. Engine health and version metadata.
- `aqef validator list` wraps `GET /projects/{project}/validators`. Local Custom Validator inventory for Volume V.
- `aqef validator register` wraps `POST /projects/{project}/validators`. Local declarative Custom Validator registration for Volume V.
