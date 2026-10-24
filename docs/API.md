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
- `GET .../executions/{id}/results`: empty list until assessment is implemented.

Missing/invalid authentication returns 401, missing permission 403, missing Execution
404, invalid request fields 422. Finished records cannot be updated or deleted. Their
frozen configuration and Evidence remain readable even after live configuration deletion.

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
