"""Small defects found by the specification-only slice 6 review."""
import pytest

from test_execution import harness, project, HEADERS
from test_decision import gate


@pytest.mark.parametrize("path", ["/healthz", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"])
def test_c4_system_operations_require_a_resolved_principal(harness, path):
    _, client, _ = harness
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization":"Bearer unknown"}).status_code == 401
    assert client.get(path, headers=HEADERS).status_code == 200


def test_a8_b2_static_row_variables_are_required_even_for_empty_variables(harness):
    _, client, _ = harness
    payload = project()
    payload["datasets"] = [{"name":"d", "version":"1", "source":"static", "rows":[{"id":"r"}]}]
    rejected = client.post("/projects", json=payload, headers=HEADERS)
    assert rejected.status_code == 422
    assert any(e["loc"][-1] == "variables" for e in rejected.json()["detail"])
    payload["datasets"][0]["rows"][0]["variables"] = {}
    assert client.post("/projects", json=payload, headers=HEADERS).status_code == 201


@pytest.mark.parametrize("owner", [None, "unknown", "other-bot"])
def test_xii_c4_service_account_owner_resolves_to_a_person_at_load(harness, owner):
    _, client, _ = harness
    other = {"id":"other-bot", "name":"Other", "kind":"service_account", "owner_person_id":"admin"}
    assert client.post("/principals",json=other,headers=HEADERS).status_code == 201
    request = {"id":"bot", "name":"Bot", "kind":"service_account", "owner_person_id":owner}
    rejected=client.post("/principals",json=request,headers=HEADERS)
    assert rejected.status_code == 422
    assert "owner_person_id" in rejected.text
    request["owner_person_id"]="admin"
    assert client.post("/principals",json=request,headers=HEADERS).status_code == 201


@pytest.mark.parametrize("path", ["/projects", "/teams", "/roles", "/projects/p/environments",
    "/projects/p/suites", "/projects/p/contracts", "/projects/p/datasets", "/projects/p/gates",
    "/projects/p/audit", "/projects/p/approvals"])
def test_c6_older_collections_use_same_bounded_offset_limit(harness, path):
    """C.6 unbounded lists, including governance history, cannot ignore pagination."""
    _, client, _ = harness
    payload=project()
    payload["datasets"]=[{"name":"d", "version":"1", "source":"static", "rows":[]}]
    payload["quality_gates"]=[gate()]
    assert client.post("/projects",json=payload,headers=HEADERS).status_code == 201
    if path.endswith("/audit"):
        # D-6 now audits reads too; select stable mutation history while checking pages.
        path += "?action=contract_define"
    separator = "&" if "?" in path else "?"
    all_rows=client.get(path,headers=HEADERS).json()
    assert all_rows
    assert client.get(path+separator+"limit=1",headers=HEADERS).json() == all_rows[:1]
    assert client.get(path+separator+"offset=1&limit=1",headers=HEADERS).json() == all_rows[1:2]
    assert client.get(path+separator+"offset=1000",headers=HEADERS).json() == []
    for bad in ("offset=-1", "limit=0", "limit=1001"):
        assert client.get(path+separator+bad,headers=HEADERS).status_code == 422
