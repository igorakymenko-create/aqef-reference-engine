"""Volume IV and A.4/A.8 materialization and XII data access."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from engine.main import create_app
from test_execution import HEADERS, project


DATASETS = "/projects/p/datasets"
EXECUTIONS = "/projects/p/executions"
GEN = {"name": "generated", "version": "1", "source": "generated",
       "generator": {"model": "generator-v1", "seed": 11, "instruction": "Produce Rows"}}
CAP = {"name": "replay", "version": "1", "source": "production_replay",
       "capture": {"source": "logs", "date_range": ["2026-10-01", "2026-10-31"],
                   "sampling": "random", "sample_size": 1, "anonymization": True}}
ROWS = [{"id": "r1", "variables": {"who": "Dataset row"}}]
TRANSCRIPT = {"turns": [{"prompt": "First {{literal}}", "response": "historical response"},
                        {"prompt": "Second user turn", "response": "historical follow-up"}]}
CAPTURE = {"conversations": [{"id": "r1", "anonymized": True, "conversation": TRANSCRIPT}]}


@pytest.fixture
def sources(monkeypatch, tmp_path):
    calls = []
    replies = {"/generate": (200, {"rows": ROWS}), "/capture": (200, CAPTURE),
               "/subject": (200, {"response": "current response", "complete": True})}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            status, data = replies[self.path]
            payload = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as stub:
        thread = Thread(target=stub.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{stub.server_port}"
            monkeypatch.setenv("AQEF_PROVIDER_URLS", json.dumps({
                "subject-v1": url + "/subject", "generator-v1": url + "/generate",
            }))
            monkeypatch.setenv("AQEF_CAPTURE_URLS", json.dumps({"logs": url + "/capture"}))
            monkeypatch.delenv("AQEF_CAPTURE_ALLOW_RAW", raising=False)
            db = str(tmp_path / "engine.db")
            with TestClient(create_app(db)) as api:
                assert api.post("/projects", json=project(), headers=HEADERS).status_code == 201
                yield api, calls, replies, db
        finally:
            stub.shutdown()
            thread.join()


def bind(api, dataset, *, replay=False):
    config = project()
    scenario = config["suites"][0]["scenarios"][0]
    scenario.pop("variables")
    if replay:
        scenario.pop("prompt")
    scenario["dataset"] = dataset
    response = api.put("/projects/p", json=config, headers=HEADERS)
    assert response.status_code == 200, response.text


def run(api, headers=HEADERS):
    return api.post(EXECUTIONS, headers=headers, json={"suite": "s", "environment": "test"})


def recorded_versions(api):
    response = api.get("/projects/p/audit?action=dataset_create", headers=HEADERS)
    assert response.status_code == 200
    return {(item["details"]["dataset"], item["details"]["version"]) for item in response.json()}


def test_iv_generated_versions_provenance_and_pinned_reruns(sources):
    api, calls, replies, db = sources
    first = api.post(DATASETS, json=GEN, headers=HEADERS)
    assert first.status_code == 201, first.text
    assert first.json()["rows"] == ROWS
    assert first.json()["generator"] == GEN["generator"]
    assert first.json()["generated_at"]
    assert calls == [("/generate", GEN["generator"])]
    assert api.post(DATASETS + "/generated/versions", json=GEN, headers=HEADERS).status_code == 409
    assert calls == [("/generate", GEN["generator"])]

    replies["/generate"] = (200, [{"id": "r2", "variables": {"who": "Latest version"}}])
    second = api.post(DATASETS + "/generated/versions", json=GEN | {"version": "2"}, headers=HEADERS)
    assert second.status_code == 201, second.text
    assert recorded_versions(api) == {("generated", "1"), ("generated", "2")}
    assert api.get(DATASETS + "/generated/rows?version=1", headers=HEADERS).json() == ROWS
    assert api.get(DATASETS + "/generated", headers=HEADERS).json() == second.json()

    bind(api, "generated@1")
    replies["/generate"] = (503, b"unavailable")
    with TestClient(create_app(db)) as restarted:
        for _ in range(2):
            result = run(restarted)
            assert result.status_code == 201, result.text
            execution = result.json()["executions"][0]
            assert execution["dataset"] == "generated@1" and execution["row_id"] == "r1"
            assert execution["variables"] == ROWS[0]["variables"]
    assert [body["prompt"] for route, body in calls if route == "/subject"] == ["Hello Dataset row"] * 2
    assert [route for route, _ in calls].count("/generate") == 2


@pytest.mark.parametrize("reply", [
    (200, {"rows": [{"variables": {}}]}),
    (200, {"rows": [{"id": "same", "variables": {}}] * 2}),
    (200, {"rows": [{"id": "missing-vars"}]}),
    (200, {"rows": [{"id": "unexpected-key", "variables": {}, "extra": True}]}),
    (200, b"not JSON"),
    (200, b'{"rows":[{"id":"x","variables":{"x":NaN}}]}'),
    (200, b'{"rows":[{"id":"x","id":"y","variables":{}}]}'),
    (503, b"upstream detail"),
])
def test_iv_failed_generation_leaves_no_version(sources, reply):
    api, _, replies, _ = sources
    replies["/generate"] = reply
    result = api.post(DATASETS, json=GEN, headers=HEADERS)
    assert result.status_code == 502
    assert "generation" in result.json()["detail"]
    assert api.get(DATASETS, headers=HEADERS).json() == []
    assert recorded_versions(api) == set()


def test_iv_reserved_or_forged_configs_fail_before_call(sources):
    api, calls, _, _ = sources
    options = [
        GEN | {"source": "synthetic"},
        GEN | {"mechanisms": [{"type": "fuzzing"}]},
        GEN | {"rows": ROWS},
        GEN | {"generated_at": "2026-11-09T00:00:00Z"},
        GEN | {"generator": GEN["generator"] | {"seed": True}},
        GEN | {"generator": GEN["generator"] | {"model": "missing"}},
    ]
    for body in options:
        assert api.post(DATASETS, json=body, headers=HEADERS).status_code == 422
    assert calls == []


def test_iv_xii_replay_uses_frozen_prompts_and_protects_derived_history(sources):
    api, calls, replies, db = sources
    assert api.post("/roles", headers=HEADERS, json={
        "name": "limited", "permissions": ["read", "execute", "dataset_create"],
    }).status_code == 201
    assert api.post("/principals", headers=HEADERS, json={
        "id": "limited", "name": "Limited", "kind": "person", "roles": ["limited"],
    }).status_code == 201
    limited = {"Authorization": "Bearer limited"}
    assert api.post(DATASETS, json=CAP, headers=limited).status_code == 403
    assert not calls
    response = api.post(DATASETS, json=CAP, headers=HEADERS)
    assert response.status_code == 201, response.text
    assert response.json()["capture"] == CAP["capture"]
    assert response.json()["captured_at"]
    assert calls == [("/capture", CAP["capture"])]
    assert api.get(DATASETS + "/replay/rows?version=1", headers=HEADERS).json() == [{
        "id": "r1", "variables": {"conversation": TRANSCRIPT},
    }]
    assert api.post(DATASETS, json=CAP, headers=HEADERS).status_code == 409

    later = deepcopy(CAPTURE)
    later["conversations"][0]["conversation"]["turns"][0]["prompt"] = "newer capture"
    replies["/capture"] = (200, later)
    assert api.post(DATASETS + "/replay/versions", json=CAP | {"version": "2"},
                    headers=HEADERS).status_code == 201
    assert recorded_versions(api) == {("replay", "1"), ("replay", "2")}

    bind(api, "replay@1", replay=True)
    assert run(api, limited).status_code == 403
    replies["/capture"] = (503, b"unavailable")
    with TestClient(create_app(db)) as restarted:
        for _ in range(2):
            response = run(restarted)
            assert response.status_code == 201, response.text
            execution = response.json()["executions"][0]
            assert execution["dataset"] == "replay@1" and execution["row_id"] == "r1"
            assert execution["conversation"] == {"turns": [
                {"prompt": "First {{literal}}", "response": "current response"},
                {"prompt": "Second user turn", "response": "current response"},
            ]}
    subject = [body for route, body in calls if route == "/subject"]
    assert [body["prompt"] for body in subject] == ["First {{literal}}", "Second user turn"] * 2
    assert subject[1]["context"] == {"turns": [
        {"prompt": "First {{literal}}", "response": "current response"},
    ]}
    assert all("historical" not in json.dumps(body) for body in subject)
    assert [route for route, _ in calls].count("/capture") == 2
    detail = f"{EXECUTIONS}/{execution['id']}"
    for path in (DATASETS, DATASETS + "/replay", DATASETS + "/replay/rows", EXECUTIONS,
                 detail, detail + "/conversation", detail + "/results", "/projects/p"):
        denied = api.get(path, headers=limited)
        assert denied.status_code == 403
        assert "production_replay_read" in denied.json()["detail"]
    assert api.get("/projects", headers=limited).json() == []
    assert api.delete("/projects/p?retain_history=true", headers=HEADERS).status_code == 204
    assert api.get(detail, headers=HEADERS).status_code == 200
    assert api.get(detail, headers=limited).status_code == 403


@pytest.mark.parametrize("reply", [
    (503, b"private upstream detail"),
    (200, {"conversations": []}),
    (200, {"conversations": [CAPTURE["conversations"][0] | {"anonymized": False}]}),
    (200, {"conversations": [{"id": "bad", "anonymized": True, "conversation": {"turns": []}}]}),
])
def test_iv_capture_failure_or_missing_attestation_leaves_no_version(sources, reply):
    api, _, replies, _ = sources
    replies["/capture"] = reply
    response = api.post(DATASETS, headers=HEADERS, json=CAP)
    assert response.status_code == 502
    assert "private upstream detail" not in response.text
    assert api.get(DATASETS, headers=HEADERS).json() == []
    assert recorded_versions(api) == set()


def test_xii_raw_capture_requires_deployment_allowlist(sources, monkeypatch):
    api, calls, replies, db = sources
    raw = CAP | {"capture": CAP["capture"] | {"anonymization": False}}
    assert api.post(DATASETS, headers=HEADERS, json=raw).status_code == 422
    assert calls == []
    monkeypatch.setenv("AQEF_CAPTURE_ALLOW_RAW", '["logs"]')
    replies["/capture"] = (200, {"conversations": [
        CAPTURE["conversations"][0] | {"anonymized": False},
    ]})
    with TestClient(create_app(db)) as opted_in:
        response = opted_in.post(DATASETS, headers=HEADERS, json=raw)
        assert response.status_code == 201, response.text
        assert response.json()["capture"]["anonymization"] is False


def test_a4_prompt_rule_uses_resolved_dataset_source(sources):
    api, _, _, _ = sources
    assert api.post(DATASETS, json=GEN, headers=HEADERS).status_code == 201
    assert api.post(DATASETS, json=CAP, headers=HEADERS).status_code == 201
    for ref, prompt in [("generated@1", None), ("replay@1", {"template": "not replay"}),
                        ("replay", None), ("replay@missing", None)]:
        scenario = {"name": "other", "dataset": ref}
        if prompt:
            scenario["prompt"] = prompt
        response = api.post("/projects/p/suites/s/scenarios", headers=HEADERS, json=scenario)
        assert response.status_code == 422, response.text
