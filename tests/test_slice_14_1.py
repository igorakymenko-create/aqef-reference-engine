"""Appendix A Project Dataset declarations and Volume IV versioning."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Event

import pytest

from test_execution import HEADERS, project
from test_slice_14 import CAP, CAPTURE, DATASETS, GEN, ROWS, sources


def inline_config(dataset, *, name="inline"):
    body = project()
    body["name"] = name
    body["datasets"] = [deepcopy(dataset)]
    scenario = body["suites"][0]["scenarios"][0]
    scenario.pop("variables")
    scenario["dataset"] = f"{dataset['name']}@{dataset['version']}"
    if dataset["source"] == "production_replay":
        scenario.pop("prompt")
    return body


def comparable_provenance(dataset):
    return {key: value for key, value in dataset.items()
            if key not in ("generated_at", "captured_at")}


@pytest.mark.parametrize("definition,endpoint", [(GEN, "/generate"), (CAP, "/capture")])
def test_a1_inline_materializes_with_api_provenance_and_reuses_pinned_version(
    sources, definition, endpoint,
):
    api, calls, _, _ = sources
    registered = api.post(DATASETS, json=definition, headers=HEADERS)
    assert registered.status_code == 201, registered.text
    body = inline_config(definition | {"rows": []})
    loaded = api.post("/projects", json=body, headers=HEADERS)
    assert loaded.status_code == 201, loaded.text
    stored = loaded.json()["datasets"][0]
    assert comparable_provenance(stored) == comparable_provenance(registered.json())
    timestamp = "captured_at" if endpoint == "/capture" else "generated_at"
    assert stored[timestamp]
    dataset_path = f"/projects/inline/datasets/{definition['name']}?version=1"
    assert api.get(dataset_path, headers=HEADERS).json() == stored

    execution = api.post("/projects/inline/executions", headers=HEADERS,
                         json={"suite": "s", "environment": "test"})
    assert execution.status_code == 201, execution.text
    assert execution.json()["executions"][0]["status"] == "completed"
    assert execution.json()["executions"][0]["row_id"] == "r1"
    assert sum(route == endpoint for route, _ in calls) == 2

    body["datasets"][0].pop("rows")
    assert api.post("/projects", json=body, headers=HEADERS).status_code == 409
    for _ in range(2):
        replaced = api.put("/projects/inline", json=body, headers=HEADERS)
        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["datasets"][0] == stored
    assert sum(route == endpoint for route, _ in calls) == 2
    audit = api.get("/projects/inline/audit?action=dataset_create", headers=HEADERS).json()
    assert [(entry["details"]["dataset"], entry["details"]["version"]) for entry in audit] == [
        (definition["name"], "1"),
    ]


def test_a1_inline_capture_requires_replay_permission_and_protects_project(sources):
    api, calls, _, _ = sources
    permissions = ["project_create", "project_edit", "contract_define", "dataset_create", "read"]
    for name, grants in [("limited-inline", permissions),
                         ("allowed-inline", permissions + ["production_replay_read"])]:
        assert api.post("/roles", headers=HEADERS, json={
            "name": name, "permissions": grants,
        }).status_code == 201
        assert api.post("/principals", headers=HEADERS, json={
            "id": name, "name": name, "kind": "person", "roles": [name],
        }).status_code == 201
    denied_headers = {"Authorization": "Bearer limited-inline"}
    allowed_headers = {"Authorization": "Bearer allowed-inline"}
    body = inline_config(CAP)
    denied = api.post("/projects", json=body, headers=denied_headers)
    assert denied.status_code == 403 and "production_replay_read" in denied.text
    assert calls == []
    assert api.get("/projects/inline", headers=HEADERS).status_code == 404
    allowed = api.post("/projects", json=body, headers=allowed_headers)
    assert allowed.status_code == 201, allowed.text
    assert api.get("/projects/inline/datasets/replay/rows", headers=denied_headers).status_code == 403
    assert api.get("/projects/inline/datasets/replay/rows", headers=allowed_headers).status_code == 200


@pytest.mark.parametrize("reply", [
    (503, b"failed"),
    (200, {"rows": [{"variables": {}}]}),
    (200, {"rows": ROWS * 2}),
    (200, b"not JSON"),
])
def test_a1_failed_inline_generation_rejects_entire_load(sources, reply):
    api, _, replies, _ = sources
    replies["/generate"] = reply
    response = api.post("/projects", headers=HEADERS, json=inline_config(GEN))
    assert response.status_code == 502 and "generation" in response.text
    assert api.get("/projects/inline", headers=HEADERS).status_code == 404
    assert api.get("/projects/inline/datasets", headers=HEADERS).json() == []
    assert api.get("/projects/inline/audit", headers=HEADERS).json() == []


def test_a1_late_validation_and_capture_failure_roll_back_all_staged_versions(sources):
    api, calls, replies, _ = sources
    before = api.get("/projects/p", headers=HEADERS).json()
    body = inline_config(GEN, name="p")
    body["datasets"].append(CAP)
    body["suites"][0]["scenarios"][0]["prompt"]["template"] = "Hello {{missing}}"
    failed = api.put("/projects/p", headers=HEADERS, json=body)
    assert failed.status_code == 422 and "missing" in failed.text
    assert [route for route, _ in calls] == ["/generate", "/capture"]
    assert api.get("/projects/p", headers=HEADERS).json() == before
    assert api.get(DATASETS, headers=HEADERS).json() == []

    body["suites"][0]["scenarios"][0]["prompt"]["template"] = "Hello {{who}}"
    replies["/capture"] = (503, b"failed")
    failed = api.put("/projects/p", headers=HEADERS, json=body)
    assert failed.status_code == 502 and "capture" in failed.text
    assert api.get("/projects/p", headers=HEADERS).json() == before
    assert api.get(DATASETS, headers=HEADERS).json() == []


@pytest.mark.parametrize("definition,field,changed", [
    (GEN, "generator", GEN["generator"] | {"instruction": "different"}),
    (CAP, "capture", CAP["capture"] | {"sampling": "stratified"}),
])
def test_b3_conflicting_inline_redeclaration_preserves_registered_version(
    sources, definition, field, changed,
):
    api, calls, _, _ = sources
    registered = api.post(DATASETS, headers=HEADERS, json=definition)
    assert registered.status_code == 201
    body = inline_config(definition, name="p")
    accepted = api.put("/projects/p", headers=HEADERS, json=body)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["datasets"][0] == registered.json()
    body["datasets"][0][field] = changed
    result = api.put("/projects/p", headers=HEADERS, json=body)
    assert result.status_code == 409
    assert api.get("/projects/p", headers=HEADERS).json() == accepted.json()
    assert api.get(DATASETS + "/" + definition["name"], headers=HEADERS).json() == registered.json()
    assert len(calls) == 1


@pytest.mark.parametrize("matching", [False, True])
def test_b3_rechecks_registry_after_waiting_for_provider(sources, monkeypatch, matching):
    api, _, _, _ = sources
    started, release = Event(), Event()
    call = api.app.state.provider.call

    async def pause_inline(model, payload, timeout, **options):
        if not started.is_set() and payload.get("instruction") == GEN["generator"]["instruction"]:
            started.set()
            assert await asyncio.to_thread(release.wait, 10)
        return await call(model, payload, timeout, **options)

    monkeypatch.setattr(api.app.state.provider, "call", pause_inline)
    before = api.get("/projects/p", headers=HEADERS).json()
    body = inline_config(GEN, name="p")
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(api.put, "/projects/p", headers=HEADERS, json=body)
        try:
            assert started.wait(10)
            assert api.get(DATASETS, headers=HEADERS).json() == []
            assert api.get("/projects/p", headers=HEADERS).json() == before
            competing = GEN if matching else (
                GEN | {"generator": GEN["generator"] | {"instruction": "Register first"}}
            )
            winner = api.post(DATASETS, headers=HEADERS, json=competing)
            assert winner.status_code == 201, winner.text
        finally:
            release.set()
        result = pending.result(timeout=10)
        assert result.status_code == (200 if matching else 409), result.text
    if matching:
        assert result.json()["datasets"] == [winner.json()]
    else:
        assert api.get("/projects/p", headers=HEADERS).json() == before
    assert api.get(DATASETS, headers=HEADERS).json() == [winner.json()]
    audit = api.get("/projects/p/audit?action=dataset_create", headers=HEADERS).json()
    assert [entry["details"]["version"] for entry in audit] == ["1"]


@pytest.mark.parametrize("inline", [False, True])
def test_a8_same_identifier_is_accepted_with_finding_and_warning(sources, inline):
    api, calls, replies, _ = sources
    replies["/subject"] = (200, {"rows": ROWS})
    definition = GEN | {"generator": GEN["generator"] | {"model": "subject-v1"}}
    path, body = ("/projects", inline_config(definition)) if inline else (DATASETS, definition)
    response = api.post(path, headers=HEADERS, json=body)
    assert response.status_code == 201, response.text
    warnings = json.loads(response.headers["X-AQEF-Warnings"])
    assert [(w["dataset"], w["version"], w["code"]) for w in warnings] == [
        ("generated", "1", "same_identifier_as_subject"),
    ]
    stored_path = "/projects/inline/datasets/generated" if inline else DATASETS + "/generated"
    assert api.get(stored_path, headers=HEADERS).json()["independence"] == warnings[0]["code"]
    assert calls == [("/subject", definition["generator"])]


@pytest.mark.parametrize("definition", [
    GEN | {"rows": ROWS},
    CAP | {"rows": [{"id": "r1", "variables": {"conversation": CAPTURE["conversations"][0]["conversation"]}}]},
    GEN | {"generated_at": "2026-11-09T00:00:00Z"},
])
def test_a1_inline_refuses_forged_rows_or_provenance(sources, definition):
    api, calls, _, _ = sources
    response = api.post("/projects", json=inline_config(definition), headers=HEADERS)
    assert response.status_code == 422
    assert calls == []
