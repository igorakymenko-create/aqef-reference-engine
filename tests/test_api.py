"""API Endpoints and Integration Tests for Slice 1.

Section references:
- Appendix C §C.1–§C.6, §C.8
- Volume XII — Governance (§Approval Workflow, §Audit, §Principals)
"""

import pytest
from fastapi.testclient import TestClient
from engine.main import create_app
from engine.models.principal import PrincipalKind


@pytest.fixture
def client():
    app = create_app(db_path=":memory:")
    return TestClient(app)


def test_auth_missing_token_returns_401(client):
    # Appendix C §C.4:
    # "All API operations MUST be authenticated... If unauthenticated, reject with 401."
    res = client.get("/projects")
    assert res.status_code == 401


def test_auth_invalid_token_returns_401(client):
    # Appendix C §C.4:
    res = client.get("/projects", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401


def test_governance_teams_and_roles_api(client):
    # Appendix C §C.3 (Governance Resources):
    headers = {"Authorization": "Bearer admin-token"}

    # Create Team
    res = client.post("/teams", json={"id": "red-team", "name": "Red Team", "description": "Security testing"}, headers=headers)
    assert res.status_code == 201
    assert res.json()["id"] == "red-team"

    # List Teams
    res = client.get("/teams", headers=headers)
    assert res.status_code == 200
    team_ids = [t["id"] for t in res.json()]
    assert "red-team" in team_ids

    # Create Role
    res = client.post(
        "/roles",
        json={"name": "lead_qa", "permissions": ["read", "project_create", "suite_create", "scenario_create", "contract_define"]},
        headers=headers,
    )
    assert res.status_code == 201

    # List Roles
    res = client.get("/roles", headers=headers)
    assert res.status_code == 200
    role_names = [r["name"] for r in res.json()]
    assert "lead_qa" in role_names


def test_project_crud_lifecycle(client):
    # Appendix C §C.3 (Project resource)
    headers = {"Authorization": "Bearer admin-token"}

    project_payload = {
        "name": "project_apollo",
        "environments": [
            {
                "name": "staging",
                "model_version": "claude-3-5-sonnet",
                "prompt_version": "v1.0",
                "tool_configuration": None,
                "infra_target": "us-east-1",
            }
        ],
        "suites": [],
        "contracts": [],
        "quality_gates": [],
    }

    # Create Project
    res = client.post("/projects", json=project_payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == "project_apollo"

    # Get Project
    res = client.get("/projects/project_apollo", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "project_apollo"

    # List Projects
    res = client.get("/projects", headers=headers)
    assert res.status_code == 200
    names = [p["name"] for p in res.json()]
    assert "project_apollo" in names

    # Delete Project
    res = client.delete("/projects/project_apollo?retain_history=true", headers=headers)
    assert res.status_code == 204

    # Verify 404 after deletion
    res = client.get("/projects/project_apollo", headers=headers)
    assert res.status_code == 404


def test_reusable_contracts_and_governance_approval(client):
    # Appendix C §C.3, §C.5 (Contract resource & Governance side effects):
    # Creating a contract requires contract_define and produces an Approval and Audit record
    headers = {"Authorization": "Bearer admin-token"}

    # Setup project first
    client.post(
        "/projects",
        json={
            "name": "proj_contracts",
            "environments": [
                {
                    "name": "dev",
                    "model_version": "gpt-4o-mini",
                    "prompt_version": "v1",
                    "tool_configuration": None,
                    "infra_target": "local",
                }
            ],
        },
        headers=headers,
    )

    contract_payload = {
        "name": "safety_standard",
        "constraints": [
            {
                "id": "no_forbidden_phrases",
                "validator": "forbidden-content",
                "target": "response",
                "expected": {"patterns": ["hate speech", "exploit"]},
            }
        ],
        "expectations": [],
    }

    # POST Contract
    res = client.post("/projects/proj_contracts/contracts", json=contract_payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == "safety_standard"

    # Retrieve Contract
    res = client.get("/projects/proj_contracts/contracts/safety_standard", headers=headers)
    assert res.status_code == 200
    assert len(res.json()["constraints"]) == 1

    # Check that Approval record was generated as a side effect
    res = client.get("/projects/proj_contracts/approvals", headers=headers)
    assert res.status_code == 200
    approvals = res.json()
    assert len(approvals) == 1
    assert approvals[0]["action"] == "contract_define"
    assert approvals[0]["approved_by"] == "admin"

    # Check that Audit log entry was generated
    res = client.get("/projects/proj_contracts/audit?action=contract_define", headers=headers)
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) == 1
    assert logs[0]["action"] == "contract_define"
    assert logs[0]["principal_id"] == "admin"


def test_dataset_versioning_and_pagination_api(client):
    # Appendix C §C.3, §C.6 (Dataset resource & pagination)
    headers = {"Authorization": "Bearer admin-token"}

    # Setup project
    client.post(
        "/projects",
        json={
            "name": "proj_data",
            "environments": [
                {
                    "name": "dev",
                    "model_version": "m1",
                    "prompt_version": "p1",
                    "tool_configuration": None,
                    "infra_target": "local",
                }
            ],
        },
        headers=headers,
    )

    # 1. Create dataset v1.0.0 with 5 rows
    rows = [{"id": f"row_{i}", "variables": {"x": i}} for i in range(5)]
    ds_payload = {
        "name": "math_dataset",
        "version": "1.0.0",
        "source": "static",
        "rows": rows,
    }
    res = client.post("/projects/proj_data/datasets", json=ds_payload, headers=headers)
    assert res.status_code == 201

    # 2. Get dataset rows with pagination (offset=2, limit=2)
    res = client.get("/projects/proj_data/datasets/math_dataset/rows?offset=2&limit=2", headers=headers)
    assert res.status_code == 200
    returned_rows = res.json()
    assert len(returned_rows) == 2
    assert returned_rows[0]["id"] == "row_2"
    assert returned_rows[1]["id"] == "row_3"

    # 3. Create new version v1.1.0
    v2_payload = {
        "name": "math_dataset",
        "version": "1.1.0",
        "source": "static",
        "rows": [{"id": "row_new", "variables": {"x": 100}}],
    }
    res = client.post("/projects/proj_data/datasets/math_dataset/versions", json=v2_payload, headers=headers)
    assert res.status_code == 201

    # 4. Attempting duplicate version fails with 409 Conflict
    res = client.post("/projects/proj_data/datasets/math_dataset/versions", json=v2_payload, headers=headers)
    assert res.status_code == 409


def test_quality_gates_api(client):
    # Appendix C §C.3, §C.5 (Quality Gate resource & Approval Workflow)
    headers = {"Authorization": "Bearer admin-token"}

    client.post(
        "/projects",
        json={
            "name": "proj_gates",
            "suites": [{"name":"s", "scenarios":[{"name":"a", "prompt":{"template":"hello"},
                "contract":{"constraints":[{"validator":"forbidden-content", "target":"response",
                    "expected":{"patterns":[]}}]}}]}],
            "environments": [
                {
                    "name": "dev",
                    "model_version": "m1",
                    "prompt_version": "p1",
                    "tool_configuration": None,
                    "infra_target": "local",
                }
            ],
        },
        headers=headers,
    )

    gate_payload = {
        "name": "security_gate",
        "aggregate": "safety",
        "threshold": 1.0,
        "on_failure": "block_release",
        "min_basis": {"results": 10, "scenarios": 2},
    }

    # POST Gate
    res = client.post("/projects/proj_gates/gates", json=gate_payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == "security_gate"

    # GET Gates
    res = client.get("/projects/proj_gates/gates", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1

    # PUT Gate (Update threshold)
    gate_payload["threshold"] = 0.99
    res = client.put("/projects/proj_gates/gates/security_gate", json=gate_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["threshold"] == 0.99

    # Verify audit log captures both gate mutations under contract_define
    res = client.get("/projects/proj_gates/audit?action=contract_define", headers=headers)
    assert res.status_code == 200
    gate_entries = [entry for entry in res.json() if "/gates" in entry["details"]["target"]]
    assert len(gate_entries) == 2
    assert all(entry["action"] == "contract_define" for entry in gate_entries)


def test_defect_1_omitted_tool_configuration_rejected(client):
    # Defect D-1: Appendix A §A.2 (Environment)
    # tool_configuration is a required field whose value may be null.
    # Omitting the key entirely MUST be rejected with 422.
    headers = {"Authorization": "Bearer admin-token"}
    payload_omitted = {
        "name": "proj_d1",
        "environments": [
            {
                "name": "staging",
                "model_version": "gpt-4o",
                "prompt_version": "v1.0",
                # "tool_configuration" key is omitted
                "infra_target": "us-east-1",
            }
        ],
    }
    res = client.post("/projects", json=payload_omitted, headers=headers)
    assert res.status_code == 422
    assert "tool_configuration" in str(res.json())

    # Explicit null MUST be accepted (Single-LLM case)
    payload_explicit_null = {
        "name": "proj_d1_valid",
        "environments": [
            {
                "name": "staging",
                "model_version": "gpt-4o",
                "prompt_version": "v1.0",
                "tool_configuration": None,
                "infra_target": "us-east-1",
            }
        ],
    }
    res = client.post("/projects", json=payload_explicit_null, headers=headers)
    assert res.status_code == 201


def test_defect_2_mechanism_config_without_type_rejected(client):
    # Defect D-2: Appendix A §A.8 (Dataset, MechanismConfig)
    # type | String | MUST | data_mutation, fuzzing, edge_cases, or adversarial
    # A MechanismConfig without type MUST be rejected with 422.
    headers = {"Authorization": "Bearer admin-token"}
    payload_no_type = {
        "name": "proj_d2",
        "environments": [
            {
                "name": "staging",
                "model_version": "gpt-4o",
                "prompt_version": "v1.0",
                "tool_configuration": None,
                "infra_target": "us-east-1",
            }
        ],
        "datasets": [
            {
                "name": "test_ds",
                "version": "1.0",
                "source": "static",
                "rows": [{"id": "r1", "variables": {}}],
                "mechanisms": [{}],  # Missing type!
            }
        ],
    }
    res = client.post("/projects", json=payload_no_type, headers=headers)
    assert res.status_code == 422
    assert "type" in str(res.json())

    # Valid MechanismConfig with type MUST be accepted and preserved
    payload_with_type = {
        "name": "proj_d2_valid",
        "environments": [
            {
                "name": "staging",
                "model_version": "gpt-4o",
                "prompt_version": "v1.0",
                "tool_configuration": None,
                "infra_target": "us-east-1",
            }
        ],
        "datasets": [
            {
                "name": "test_ds",
                "version": "1.0",
                "source": "static",
                "rows": [{"id": "r1", "variables": {}}],
                "mechanisms": [{"type": "data_mutation"}],
            }
        ],
    }
    res = client.post("/projects", json=payload_with_type, headers=headers)
    assert res.status_code == 201
    created_proj = res.json()
    assert created_proj["datasets"][0]["mechanisms"][0]["type"] == "data_mutation"


def test_defect_2_unknown_field_rejected(client):
    # Defect D-2 check: Appendix A introduction
    # Unrecognized configuration keys MUST NOT be silently dropped; they must be rejected naming the key.
    headers = {"Authorization": "Bearer admin-token"}
    payload = {
        "name": "proj_unknown_key",
        "unrecognized_field": "some_value",
        "environments": [
            {
                "name": "staging",
                "model_version": "gpt-4o",
                "prompt_version": "v1.0",
                "tool_configuration": None,
                "infra_target": "us-east-1",
            }
        ],
    }
    res = client.post("/projects", json=payload, headers=headers)
    assert res.status_code == 422
    assert "unrecognized_field" in str(res.json())
