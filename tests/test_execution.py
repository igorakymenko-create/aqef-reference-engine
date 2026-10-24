"""Slice 2 rules 1–8: execution/evidence, without assessment or conformance material."""
import asyncio
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest
from fastapi.testclient import TestClient

from engine.execution import duration, render
from engine.main import create_app
from engine.models.principal import Principal, PrincipalKind, Role
from engine.providers import load_provider_urls
from engine.storage import StorageConflictError


HEADERS = {"Authorization": "Bearer admin-token"}
BASE = "/projects/p/executions"


def project():
    return {"name": "p", "environments": [{"name": "test", "model_version": "subject-v1",
            "prompt_version": "v1", "tool_configuration": None, "infra_target": "local"}],
            "contracts": [{"name": "c", "constraints": [{"id": "shape", "validator": "structural",
                             "target": "response", "expected": "anything"}]}],
            "suites": [{"name": "s", "scenarios": [{"name": "a", "prompt": {"template": "Hello {{who}}"},
                                                          "variables": {"who": "world"}}]}]}


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv("AQEF_PROVIDER_URLS", '{"subject-v1":"http://127.0.0.1:9999/subject"}')
    app = create_app()
    client = TestClient(app)
    calls = []

    async def call(model, payload, timeout):
        calls.append(deepcopy(payload))
        return {"response": "bad answer", "usage": {"total_tokens": 9}, "artifacts": {"log": "raw"}}
    monkeypatch.setattr(app.state.provider, "call", call)
    return app, client, calls


def configure(harness, payload=None):
    app, client, calls = harness
    response = client.post("/projects", json=payload or project(), headers=HEADERS)
    assert response.status_code == 201, response.text
    return app, client, calls


def run(client):
    response = client.post(BASE, json={"suite": "s", "environment": "test"}, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def test_single_turn_evidence_and_frozen_runtime(harness):
    app, client, calls = configure(harness)
    batch = run(client)
    r = batch["executions"][0]
    assert r["status"] == "completed"
    assert r["execution_batch_id"] == batch["execution_batch_id"]
    assert r["scheduling"]["requested_by"] == "admin"
    assert r["conversation"] == {"turns": [{"prompt": "Hello world", "response": "bad answer"}]}
    assert calls[0] == {"model": "subject-v1", "prompt": "Hello world", "variables": {"who": "world"},
                        "environment": project()["environments"][0] | {"action_boundary": None}, "context": {"turns": []}}
    path = BASE + "/" + r["id"]
    assert client.get(path, headers=HEADERS).json() == r
    assert client.get(path + "/conversation", headers=HEADERS).json() == r["conversation"]
    artifacts = client.get(path + "/artifacts", headers=HEADERS).json()
    assert [a["name"] for a in artifacts] == ["latency_ms", "log", "usage"]
    assert artifacts[0]["data"] >= 0
    assert client.get(path + "/artifacts?offset=1&limit=1", headers=HEADERS).json() == artifacts[1:2]
    # Slice 3 now assesses completed Evidence; the old placeholder format is not a
    # valid structural rule, so its missing check yields an unavailable Validator.
    results = client.get(path + "/results", headers=HEADERS).json()
    assert len(results) == 1
    assert results[0]["confidence"] == "not_applicable"
    assert results[0]["disposition"] == "oracle_unavailable"
    with pytest.raises(StorageConflictError):
        app.state.storage.update_execution(r)
    assert client.delete("/projects/p?retain_history=true", headers=HEADERS).status_code == 204
    assert client.get(path, headers=HEADERS).json() == r
    assert client.get(path + "/conversation", headers=HEADERS).status_code == 200


def test_dataset_batches_and_preflight_all_rows(harness):
    p = project()
    p["datasets"] = [{"name": "d", "version": "v1", "source": "static", "rows": [
        {"id": "r2", "variables": {"who": "two"}}, {"id": "r1", "variables": {"who": "one"}}]}]
    sc = p["suites"][0]["scenarios"][0]
    sc.pop("variables")
    sc["dataset"] = "d@v1"
    app, client, calls = configure(harness, p)
    records = run(client)["executions"]
    assert [r["row_id"] for r in records] == ["r2", "r1"]
    assert [c["prompt"] for c in calls] == ["Hello two", "Hello one"]
    assert [r["scheduling"]["order"] for r in records] == [0, 1]
    assert len({r["id"] for r in records}) == 2
    # Corrupt a row after load to exercise execution preflight, without invoking any subject.
    ds = app.state.storage.get_dataset("p", "d", "v1")
    ds.rows[1].variables = {}
    with app.state.storage._get_connection() as conn:
        conn.execute("UPDATE datasets SET data_json = ?", (ds.model_dump_json(),))
    calls.clear()
    assert client.post(BASE, json={"suite": "s", "environment": "test"}, headers=HEADERS).status_code == 422
    assert not calls
    assert len(app.state.storage.list_executions("p")) == 2


def test_settings_field_inheritance_and_repeatable_prompts(harness):
    p = project()
    p["execution"] = {"timeout": "2s", "scheduling": "parallel", "parallelization": 3,
                      "retry": {"max_attempts": 2, "on": "infrastructure_failure"}}
    p["suites"][0]["execution"] = {"scheduling": "sequential"}
    _, client, calls = configure(harness, p)
    first = run(client)["executions"][0]
    second = run(client)["executions"][0]
    assert first["id"] != second["id"]
    assert calls[0] == calls[1]
    assert first["configuration"] == second["configuration"]
    assert first["configuration"]["execution"] == p["execution"] | {"scheduling": "sequential"}


@pytest.mark.parametrize("failures,expected_calls,status", [(1, 2, "completed"), (3, 3, "infrastructure_failure")])
def test_infrastructure_retry_budget(harness, monkeypatch, failures, expected_calls, status):
    p = project()
    p["execution"] = {"retry": {"max_attempts": 2, "on": "infrastructure_failure"}}
    app, client, calls = configure(harness, p)

    async def call(model, payload, timeout):
        calls.append(payload)
        if len(calls) <= failures:
            raise httpx.ConnectError("offline")
        return {"response": "fail"}
    monkeypatch.setattr(app.state.provider, "call", call)
    r = run(client)["executions"][0]
    assert r["status"] == status
    assert len(calls) == expected_calls
    assert len(r["attempts"]) == expected_calls
    assert r["retry_count"] == expected_calls - 1
    assert all(a["error"] and a["completed_at"] for a in r["attempts"][:failures])
    if status == "infrastructure_failure":
        assert r["conversation"] is None
        assert client.get(BASE + "/" + r["id"] + "/conversation", headers=HEADERS).status_code == 409


@pytest.mark.parametrize("later_failure", [False, True])
def test_multiturn_context_and_no_retry_after_response(harness, monkeypatch, later_failure):
    p = project()
    p["execution"] = {"retry": {"max_attempts": 3, "on": "infrastructure_failure"}}
    app, client, calls = configure(harness, p)

    async def call(model, payload, timeout):
        calls.append(deepcopy(payload))
        if len(calls) == 1:
            return {"response": "first", "complete": False, "artifacts": {"retrieval": "document"}}
        if later_failure:
            raise httpx.ReadTimeout("later turn failed")
        return {"response": "last"}
    monkeypatch.setattr(app.state.provider, "call", call)
    r = run(client)["executions"][0]
    assert len(calls) == 2
    assert calls[1]["prompt"] == "Continue."
    assert calls[1]["context"] == {"turns": [{"prompt": "Hello world", "response": "first"}]}
    assert r["retry_count"] == 0
    assert any(a["name"] == "retrieval" for a in r["artifacts"])
    if later_failure:
        assert r["conversation"] is None
        assert r["partial_turns"][0]["response"] == "first"
        assert r["status"] == "infrastructure_failure"
    else:
        assert len(r["conversation"]["turns"]) == 2


def test_invalid_envelope_with_genuine_response_is_not_retried(harness, monkeypatch):
    p = project()
    p["execution"] = {"retry": {"max_attempts": 2, "on": "infrastructure_failure"}}
    app, client, calls = configure(harness, p)

    async def call(*args):
        calls.append(1)
        return {"response": "unfavorable", "complete": "invalid"}
    monkeypatch.setattr(app.state.provider, "call", call)
    r = run(client)["executions"][0]
    assert len(calls) == 1
    assert r["partial_turns"][0]["response"] == "unfavorable"
    assert r["status"] == "infrastructure_failure"


def test_timeout_is_whole_execution_bound(harness, monkeypatch):
    p = project()
    p["execution"] = {"timeout": "30ms", "retry": {"max_attempts": 3, "on": "infrastructure_failure"}}
    app, client, calls = configure(harness, p)

    async def call(*args):
        calls.append(1)
        await asyncio.sleep(.2)
        return {"response": "late"}
    monkeypatch.setattr(app.state.provider, "call", call)
    r = run(client)["executions"][0]
    assert r["status"] == "infrastructure_failure"
    assert r["conversation"] is None
    assert len(calls) == 1
    assert "Timeout" in r["error"]


@pytest.mark.parametrize("strategy,expected_peak", [("parallel", 2), ("sequential", 1)])
def test_parallel_pool_and_context_isolation(harness, monkeypatch, strategy, expected_peak):
    p = project()
    p["execution"] = {"scheduling": strategy, "parallelization": 2}
    p["suites"][0]["scenarios"] = [{"name": str(i), "prompt": {"template": "{{who}}"},
                                   "variables": {"who": str(i), "nested": {"value": 0}}} for i in range(4)]
    app, client, calls = configure(harness, p)
    active = peak = 0

    async def call(model, payload, timeout):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        assert not payload["context"]["turns"]
        payload["variables"]["nested"]["value"] = 99
        payload["context"]["turns"].append({"prompt": "contamination"})
        await asyncio.sleep(.01)
        active -= 1
        return {"response": payload["prompt"]}
    monkeypatch.setattr(app.state.provider, "call", call)
    records = run(client)["executions"]
    assert peak == expected_peak
    assert [r["scenario"] for r in records] == [str(i) for i in range(4)]
    assert all(r["variables"]["nested"]["value"] == 0 for r in records)
    assert all(len(r["conversation"]["turns"]) == 1 for r in records)


def test_fixed_evidence_bypasses_subject_and_validates_shape(harness):
    p = project()
    fixed = {"conversation": {"turns": [{"prompt": "original", "response": "planted"}]},
             "artifacts": {"trace": [1, 2]}, "source_execution": "source"}
    p["suites"][0]["scenarios"] = [{"name": "control", "seeded_control": {
        "defect_class": "shape", "planted_defect": "bad", "confirmed_by": "construction"}, "evidence": fixed}]
    app, client, calls = configure(harness, p)
    app.state.provider.urls.clear()
    r = run(client)["executions"][0]
    assert not calls
    assert r["conversation"] == fixed["conversation"]
    assert r["source_execution"] == "source"
    assert r["artifacts"][0]["data"] == [1, 2]
    sc = app.state.storage.get_scenario("p", "s", "control")
    replacement = sc.model_dump(mode="json",exclude_none=True)
    replacement["evidence"]["conversation"] = {"turns": []}
    rejection = client.put("/projects/p/suites/s/scenarios/control",json=replacement,headers=HEADERS)
    assert rejection.status_code == 422
    assert "conversation" in rejection.text


def test_permissions_pagination_filters_and_errors(harness):
    app, client, calls = configure(harness)
    assert client.post(BASE, json={"suite": "s", "environment": "test"}).status_code == 401
    app.state.storage.create_role(Role(name="reader", permissions=["read"]))
    app.state.storage.create_principal(Principal(id="reader", name="Reader", kind=PrincipalKind.PERSON,
                                               roles=["reader"]), token="reader-token")
    reader = {"Authorization": "Bearer reader-token"}
    assert client.post(BASE, json={"suite": "s", "environment": "test"}, headers=reader).status_code == 403
    assert not calls
    one = run(client)["executions"][0]
    run(client)
    assert len(client.get(BASE + "?limit=1&offset=1&suite=s&environment=test&status=completed", headers=reader).json()) == 1
    assert client.get(BASE + "?suite=wrong", headers=HEADERS).json() == []
    assert client.get(BASE + "?date_to=2000-01-01T00:00:00Z", headers=HEADERS).json() == []
    assert len(client.get(BASE + "?date_from=2000-01-01T00:00:00Z", headers=HEADERS).json()) == 2
    assert client.get(BASE + "?date_from=2000-01-01", headers=HEADERS).status_code == 422
    assert client.get(BASE + "?limit=0", headers=HEADERS).status_code == 422
    assert client.get(BASE + "/missing", headers=HEADERS).status_code == 404
    assert client.get(BASE.replace("/p/", "/other/") + "/" + one["id"], headers=HEADERS).status_code == 404
    assert client.post(BASE, json={"suite": "missing", "environment": "test"}, headers=HEADERS).status_code == 404
    assert client.post(BASE, json={"suite": "s", "environment": "test", "url": "arbitrary"}, headers=HEADERS).status_code == 422


@pytest.mark.parametrize("config", [{"timeout": "0s"}, {"timeout": "forever"}, {"scheduling": "unknown"}, {"timeout": None}])
def test_invalid_runtime_settings_rejected_before_calls(harness, config):
    p = project()
    p["execution"] = config
    if config.get("timeout", "absent") is None:
        _,client,calls=harness
        response=client.post("/projects",json=p,headers=HEADERS)
        assert response.status_code==422 and "timeout" in response.text
        assert not calls
        return
    _, client, calls = configure(harness, p)
    assert client.post(BASE, json={"suite": "s", "environment": "test"}, headers=HEADERS).status_code == 422
    assert not calls


@pytest.mark.parametrize("value", ["[]", "invalid", '{"x":"file:///tmp/a"}', '{"x":3}', '{"x":"https://a/#fragment"}'])
def test_startup_mapping_validation(monkeypatch, value):
    monkeypatch.setenv("AQEF_PROVIDER_URLS", value)
    with pytest.raises(ValueError):
        create_app()


def test_mapping_frozen_at_startup_and_missing_model(harness, monkeypatch):
    app, client, calls = configure(harness)
    monkeypatch.setenv("AQEF_PROVIDER_URLS", '{}')
    assert app.state.provider.urls["subject-v1"].endswith("/subject")
    app.state.provider.urls.clear()
    response = client.post(BASE, json={"suite": "s", "environment": "test"}, headers=HEADERS)
    assert response.status_code == 422
    assert "No provider URL" in response.json()["detail"]
    assert not calls


def test_canonical_rendering_and_durations():
    assert render("{{x}}/{{ obj }}/{{missing}}", {"x": "{{obj}}", "obj": {"z": False, "a": None}, "missing": 2}) == '{{obj}}/{"a":null,"z":false}/2'
    assert duration("1ms") == .001
    assert duration("1.5m") == 90
    assert duration("1h") == 3600
    with pytest.raises(ValueError):
        render("{{missing}}", {})


def test_timeout_remaining_budget_across_turns(harness, monkeypatch):
    p = project()
    p["execution"] = {"timeout": "100ms"}
    app, client, calls = configure(harness, p)
    budgets = []

    async def call(model, payload, timeout):
        budgets.append(timeout)
        if len(budgets) == 1:
            await asyncio.sleep(.03)
            return {"response": "first", "complete": False}
        await asyncio.sleep(.2)
        return {"response": "late"}
    monkeypatch.setattr(app.state.provider, "call", call)
    record = run(client)["executions"][0]
    assert len(budgets) == 2
    assert budgets[1] < budgets[0] - .02
    assert record["conversation"] is None
    assert record["partial_turns"][0]["response"] == "first"
    assert record["retry_count"] == 0


def test_whole_batch_preflight_and_empty_dataset(harness):
    p = project()
    p["datasets"] = [{"name": "empty", "version": "v1", "source": "static", "rows": []}]
    sc = p["suites"][0]["scenarios"][0]
    sc.pop("variables")
    sc["dataset"] = "empty@v1"
    app, client, calls = configure(harness, p)
    assert run(client)["executions"] == []
    assert not calls
    assert not app.state.storage.list_executions("p")


@pytest.mark.parametrize("status,body", [(429, b'{}'), (302, b'{}'), (200, b'not json'), (200, b'{"complete":true}')])
def test_http_transport_failures(harness, monkeypatch, status, body):
    # Exercise the production HTTP transport using httpx's supported mock transport.
    app, client, calls = configure(harness)
    from engine.providers import HTTPProvider
    real_client = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=body)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(app.state.provider, "call", HTTPProvider(app.state.provider.urls).call)
    record = run(client)["executions"][0]
    assert record["status"] == "infrastructure_failure"
    assert record["conversation"] is None
    assert len(requests) == 1


def test_real_http_transport_and_restart_persistence(monkeypatch, tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"response":"real http"}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("AQEF_PROVIDER_URLS", json.dumps({"subject-v1": f"http://127.0.0.1:{server.server_port}/invoke"}))
        db = str(tmp_path / "engine.db")
        app = create_app(db)
        client = TestClient(app)
        assert client.post("/projects", json=project(), headers=HEADERS).status_code == 201
        record = run(client)["executions"][0]
        assert record["conversation"]["turns"][0]["response"] == "real http"
        assert requests[0][0] == "/invoke"
        assert requests[0][1]["prompt"] == "Hello world"
        restarted = TestClient(create_app(db))
        assert restarted.get(BASE + "/" + record["id"], headers=HEADERS).json() == record
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
