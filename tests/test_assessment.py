"""Slice 3: tests derived solely from the prose specification and recorded plan."""
import asyncio
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest
from fastapi.testclient import TestClient

from test_execution import harness, configure, project, run, HEADERS, BASE
from engine.assessment import judge_identity
from engine.main import create_app
from engine.models.assessment import Result
from engine.models.principal import Principal, PrincipalKind, Role
from engine.storage import StorageConflictError
from engine.validators import check_builtin, select_target, custom_check


def expectation(**kwargs):
    return {"id": "quality", "criteria": "The answer is correct.", "judge": {
        "model": "judge-v1", "confidence_source": "self_rating"}, "confidence_threshold": .7} | kwargs


def constraint(name="schema", target="response", expected="json", **kwargs):
    return {"validator": name, "target": target, "expected": expected} | kwargs


def assessment_project(constraints=None, expectations=None, policy="AND"):
    p = project()
    p["contracts"] = [{"name": "c", "constraints": constraints or [],
                       "expectations": [expectation()] if expectations is None else expectations,
                       "policies": {"validator_composition": policy}}]
    return p


def results(client, record, query=""):
    reply = client.get(BASE + "/" + record["id"] + "/results" + query, headers=HEADERS)
    assert reply.status_code == 200, reply.text
    return reply.json()


def install_provider(app, monkeypatch, subject='{"answer":42}', reply=None):
    calls = []
    app.state.provider.urls["judge-v1"] = "http://judge.local/invoke"

    async def call(model, payload, timeout):
        calls.append((model, deepcopy(payload)))
        if model == "subject-v1":
            return {"response": subject, "usage": {"total_tokens": 12}}
        return {"verdict": "pass", "confidence": .9, "explanation": "Checked answer", "assertions": 1} if reply is None else deepcopy(reply)
    monkeypatch.setattr(app.state.provider, "call", call)
    return calls


def test_validation_before_judge_wire_result_and_durable_history(harness, monkeypatch):
    p = assessment_project([constraint(id="shape")])
    app, client, _ = configure(harness, p)
    calls = install_provider(app, monkeypatch)
    record = run(client)["executions"][0]
    rows = results(client, record)
    assert [r["oracle_type"] for r in rows] == ["validator", "judge"]
    assert [r["clause"] for r in rows] == ["shape", "quality"]
    assert rows[0]["verdict"] == "pass"
    assert rows[0]["confidence"] == "not_applicable"
    judged = rows[1]
    assert judged["disposition"] == "actionable"
    assert judged["confidence"] == .9
    assert judged["oracle"] == judge_identity(record["configuration"]["contract"]["expectations"][0])
    assert calls[1] == ("judge-v1", {"model": "judge-v1", "criteria": "The answer is correct.",
        "confidence_source": "self_rating", "evidence": {"conversation": record["conversation"], "artifacts": record["artifacts"]}})
    for row in rows:
        assert set(row) == {"id", "execution", "clause", "oracle_type", "oracle", "verdict", "confidence",
                            "disposition", "supporting_evidence", "recorded_at"}
        assert row["execution"] == record["id"]
        with pytest.raises(StorageConflictError):
            app.state.storage.append_result("p", row)
    assert results(client, record, "?oracle_type=judge&verdict=pass&limit=1") == [judged]
    assert results(client, record, "?offset=1&limit=1") == [judged]
    assert client.delete("/projects/p?retain_history=true", headers=HEADERS).status_code == 204
    assert results(client, record) == rows


@pytest.mark.parametrize("policy,veto,missing,judge_runs", [
    ("AND", False, False, False), ("OR", False, False, True),
    ("OR", True, False, False), ("hard-veto", False, False, False),
    ("OR", False, True, False)])
def test_composition_and_unavailable_short_circuit(harness, monkeypatch, policy, veto, missing, judge_runs):
    checks = [constraint("forbidden-content", "response", {"patterns": ["answer"]}, id="forbidden", veto=veto),
              constraint("schema", "missing" if missing else "response", "json", id="shape")]
    app, client, _ = configure(harness, assessment_project(checks, policy=policy))
    calls = install_provider(app, monkeypatch)
    record = run(client)["executions"][0]
    rows = results(client, record)
    assert [r["clause"] for r in rows[:2]] == ["forbidden", "shape"]
    assert rows[0]["verdict"] == "fail"
    assert rows[0]["disposition"] == "actionable"
    assert rows[1]["verdict"] == (None if missing else "pass")
    assert len(calls) == (2 if judge_runs else 1)
    assert len(rows) == (3 if judge_runs else 2)
    if missing:
        assert rows[1]["confidence"] == "not_applicable"
        assert rows[1]["disposition"] == "oracle_unavailable"


@pytest.mark.parametrize("confidence,verdict,disposition,assertions", [
    (.69, "pass", "inconclusive", 1), (.7, "fail", "actionable", 1),
    (0, "fail", "inconclusive", 3), (1, "pass", "actionable", 12)])
def test_confidence_boundary_and_assertions(harness, monkeypatch, confidence, verdict, disposition, assertions):
    app, client, _ = configure(harness, assessment_project())
    calls = install_provider(app, monkeypatch, reply={"verdict": verdict, "confidence": confidence,
                                         "explanation": "Assessment", "assertions": assertions})
    row = results(client, run(client)["executions"][0])[0]
    assert row["verdict"] == verdict and row["confidence"] == confidence
    assert row["disposition"] == disposition
    assert ("assertions" in row) == (assertions > 1)
    if assertions > 1:
        assert row["assertions"] == assertions
    assert len(calls) == 2


@pytest.mark.parametrize("mutation", [
    {"confidence": None}, {"confidence": -1}, {"confidence": 1.1}, {"confidence": "0.8"},
    {"confidence": True}, {"confidence": float("nan")}, {"verdict": "maybe"}, {"assertions": 0},
    {"assertions": True}, {"explanation": None}, {"unknown": "extra"}, {"assertions": None}])
def test_malformed_judge_never_retried_or_implicit_pass(harness, monkeypatch, mutation):
    app, client, _ = configure(harness, assessment_project())
    reply = {"verdict": "fail", "confidence": .9, "explanation": "reason", "assertions": 1} | mutation
    calls = install_provider(app, monkeypatch, reply=reply)
    record = run(client)["executions"][0]
    row = results(client, record)[0]
    assert row["disposition"] == "oracle_unavailable"
    assert row["verdict"] is None and row["confidence"] == "not_applicable"
    assert row["supporting_evidence"]["provider_response"]["verdict"] == reply["verdict"]
    assert len(calls) == 2
    assert len(row["supporting_evidence"]["attempts"]) == 1


@pytest.mark.parametrize("failure", ["transport", "timeout", "unmapped"])
def test_unavailable_judge_preserves_evidence(harness, monkeypatch, failure):
    p = assessment_project()
    p["execution"] = {"timeout": "30ms"}
    app, client, _ = configure(harness, p)
    app.state.provider.urls["judge-v1"] = "http://judge.local"
    calls = []

    async def call(model, payload, timeout):
        calls.append(model)
        if model == "subject-v1":
            return {"response": "answer"}
        if failure == "timeout":
            await asyncio.sleep(.1)
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(app.state.provider, "call", call)
    if failure == "unmapped":
        del app.state.provider.urls["judge-v1"]
    record = run(client)["executions"][0]
    assert record["status"] == "completed"
    row = results(client, record)[0]
    assert row["disposition"] == "oracle_unavailable"
    assert row["supporting_evidence"]["evidence"]["conversation"] == record["conversation"]
    assert len(calls) == (1 if failure == "unmapped" else 2)


@pytest.mark.parametrize("name,target,expected,passed", [
    ("schema", {"a":1}, {"type":"object","required":["a"],"properties":{"a":{"type":"integer"}}}, True),
    ("schema", {"a":"wrong"}, {"type":"object","properties":{"a":{"type":"integer"}}}, False),
    ("schema", "not-json", "json", False),
    ("schema", {"a":2}, {"$defs":{"n":{"type":"integer"}},"properties":{"a":{"$ref":"#/$defs/n"}}}, True),
    ("forbidden-content", "Unsafe word", {"patterns":[{"regex":"(?i)unsafe"}]}, False),
    ("forbidden-content", "safe", {"patterns":["unsafe"]}, True),
    ("structural", {"turns":[{"prompt":"start","response":"finish"}]}, {"required_steps":["start","finish"]}, True),
    ("structural", ["finish","start"], ["start","finish"], False),
    ("latency", 500, "500ms", True), ("latency", 501, "500ms", False),
    ("cost", [{"total_tokens":2},{"total_tokens":3}], 5, True),
    ("cost", {"cost":.2}, {"metric":"cost","max":.1}, False)])
def test_pure_builtin_rules(name, target, expected, passed):
    before = deepcopy((target, expected))
    first = check_builtin(name, target, expected)
    assert first[0] == passed
    assert check_builtin(name, target, expected) == first
    assert (target, expected) == before


@pytest.mark.parametrize("name,target,expected", [
    ("schema", {}, {"$ref":"https://example.invalid/schema"}),
    ("schema", {}, {"type":"nonsense"}),
    ("forbidden-content", "text", {"patterns":[{"regex":"["}]}),
    ("structural", "text", {"unknown":[]}), ("latency", None, 10),
    ("cost", {}, 1), ("boundary", [], {}), ("tool-call", {}, {})])
def test_broken_validator_is_unavailable_not_fail(harness, monkeypatch, name, target, expected):
    app, client, _ = configure(harness, assessment_project([constraint(name, "artifacts.sample", expected)]))
    calls = []

    async def call(model, payload, timeout):
        calls.append(model)
        return {"response":"ok", "artifacts":{"sample":target}}
    monkeypatch.setattr(app.state.provider, "call", call)
    row = results(client, run(client)["executions"][0])[0]
    assert row["disposition"] == "oracle_unavailable"
    assert row["verdict"] is None
    assert "error" in row["supporting_evidence"]
    assert calls == ["subject-v1"]


def test_target_paths_and_recorded_metrics():
    record = {"conversation":{"turns":[{"prompt":"hi","response":'{"nested":[3]}'}]},
              "artifacts":[{"name":"usage","data":{"total_tokens":2}}, {"name":"usage","data":{"total_tokens":4}}],
              "duration_ms":123}
    assert select_target(record, "response.nested.0") == 3
    assert select_target(record, "conversation.turns.0.prompt") == "hi"
    assert select_target(record, "artifacts.usage.1.total_tokens") == 4
    assert select_target(record, "artifacts.*") == record["artifacts"]
    assert select_target(record, "duration_ms") == 123


def custom_definition(version="v1"):
    return {"name":"exact", "version":version, "rule":{"operation":"equals", "expected":"approved"}}


def test_custom_registration_governance_execution_and_freezing(harness, monkeypatch):
    check = constraint("exact@v1", "response", None, dimension="functional", id="custom")
    app, client, _ = configure(harness, assessment_project([check]))
    response = client.post("/projects/p/validators", json=custom_definition(), headers=HEADERS)
    assert response.status_code == 201, response.text
    assert client.get("/projects/p/validators?limit=1", headers=HEADERS).json() == [custom_definition()]
    assert client.post("/projects/p/validators", json=custom_definition(), headers=HEADERS).status_code == 409
    calls = install_provider(app, monkeypatch, subject="approved")
    first = run(client)["executions"][0]
    rows = results(client, first)
    assert rows[0]["verdict"] == "pass" and rows[1]["oracle_type"] == "judge"
    assert first["configuration"]["validators"]["exact@v1"] == custom_definition()
    assert client.post("/projects/p/validators", json=custom_definition("v2"), headers=HEADERS).status_code == 201
    assert results(client, first) == rows
    audit = app.state.storage.list_audit_logs("p")
    assert any(a.details.get("target") == "validators/exact@v1" for a in audit)


@pytest.mark.parametrize("rule", [{"operation":"http", "url":"https://invalid"},
    {"operation":"equals", "expected":1, "code":"random()"},
    {"operation":"range", "minimum":2, "maximum":1},
    {"operation":"forbidden-content", "expected":{"patterns":[{"regex":"["}]}},
    {"operation":"schema", "expected":{"$ref":"https://invalid/schema"}}])
def test_custom_invalid_registration_rejected(harness, rule):
    _, client, _ = configure(harness)
    response = client.post("/projects/p/validators", json=custom_definition() | {"rule":rule}, headers=HEADERS)
    assert response.status_code == 422


def test_custom_purity_unknown_and_version_ambiguity(harness, monkeypatch):
    app, client, _ = configure(harness, assessment_project([
        constraint("exact", "response", None, dimension="functional")]))
    install_provider(app, monkeypatch, subject="approved")
    assert results(client, run(client)["executions"][0])[0]["disposition"] == "oracle_unavailable"
    for version in ("v1", "v2"):
        assert client.post("/projects/p/validators", json=custom_definition(version), headers=HEADERS).status_code == 201
    assert results(client, run(client)["executions"][0])[0]["disposition"] == "oracle_unavailable"
    assert custom_check(4, {"operation":"range","minimum":3,"maximum":5})[0]
    assert not custom_check(True, {"operation":"equals","expected":1})[0]


def admission(**changes):
    return {"oracle":"judge-config", "reference_set":"reference@v1", "items":10,
            "verdict_distribution":{"pass":7,"fail":3}, "raw_agreement":.8, "measure":"cohen_kappa",
            "chance_corrected_agreement":.7, "threshold":.7, "admitted":True,
            "labelled_by":["admin"]} | changes


def test_admission_append_only_acceptance_order_withdrawal_and_arbitrations(harness):
    app, client, _ = configure(harness)
    assert not app.state.storage.is_admitted("p", "judge-config")
    first = client.post("/projects/p/admissions", json=admission(), headers=HEADERS)
    assert first.status_code == 201, first.text
    assert first.json()["recorded_by"] == "admin"
    assert "arbitrations" not in first.json()
    assert app.state.storage.is_admitted("p", "judge-config")
    second = client.post("/projects/p/admissions", json=admission(chance_corrected_agreement="not_computed", admitted=False, arbitrations=[]), headers=HEADERS)
    assert second.status_code == 201
    assert not app.state.storage.is_admitted("p", "judge-config")
    assert second.json()["arbitrations"] == []
    rows = client.get("/projects/p/admissions?oracle=judge-config", headers=HEADERS).json()
    assert rows == [first.json(), second.json()]
    assert client.get("/projects/p/admissions?offset=1&limit=1", headers=HEADERS).json() == [second.json()]
    with pytest.raises(StorageConflictError):
        app.state.storage.append_admission("p", first.json())
    assert client.put("/projects/p/admissions/" + first.json()["id"], json=admission(), headers=HEADERS).status_code == 404


@pytest.mark.parametrize("changes", [
    {"id":"client-id"}, {"recorded_at":"2000-01-01T00:00:00Z"}, {"recorded_by":"admin"},
    {"items":0}, {"items":True}, {"items":9}, {"verdict_distribution":{"pass":11,"fail":-1}},
    {"verdict_distribution":{"other":10}}, {"raw_agreement":-.1}, {"raw_agreement":1.1},
    {"raw_agreement":True}, {"reference_set":"unversioned"}, {"labelled_by":[]},
    {"labelled_by":["missing"]}, {"chance_corrected_agreement":None},
    {"chance_corrected_agreement":"0.7"}, {"chance_corrected_agreement":"not_computed"},
    {"admitted":False}, {"chance_corrected_agreement":.69}, {"arbitrations":None}, {"measure":" "}])
def test_admission_consistency_rejections(harness, changes):
    _, client, _ = configure(harness)
    response = client.post("/projects/p/admissions", json=admission(**changes), headers=HEADERS)
    assert response.status_code == 422, response.text


def test_admission_required_fields(harness):
    _, client, _ = configure(harness)
    for key in admission():
        data = admission()
        del data[key]
        assert client.post("/projects/p/admissions", json=data, headers=HEADERS).status_code == 422, key


def test_admission_person_only_permissions_and_custom_service_review(harness):
    app, client, _ = configure(harness)
    app.state.storage.create_role(Role(name="reviewer", permissions=["review", "contract_define"]))
    app.state.storage.create_role(Role(name="reader", permissions=["read"]))
    app.state.storage.create_principal(Principal(id="bot", name="Bot", kind=PrincipalKind.SERVICE_ACCOUNT,
        owner_person_id="admin", roles=["reviewer"]), token="bot")
    app.state.storage.create_principal(Principal(id="reader", name="Reader", kind=PrincipalKind.PERSON,
        roles=["reader"]), token="reader")
    bot = {"Authorization":"Bearer bot"}
    reader = {"Authorization":"Bearer reader"}
    assert client.post("/projects/p/admissions", json=admission(), headers=bot).status_code == 403
    assert client.post("/projects/p/admissions", json=admission(), headers=reader).status_code == 403
    assert client.post("/projects/p/admissions", json=admission()).status_code == 401
    assert client.get("/projects/p/admissions", headers=bot).status_code == 403
    assert client.post("/projects/p/validators", json=custom_definition(), headers=reader).status_code == 403
    assert client.post("/projects/p/validators", json=custom_definition(), headers=bot).status_code == 422
    assert client.post("/projects/p/validators", json=custom_definition(), headers=bot | {
        "X-Approved-By":"admin", "X-External-Review-Ref":"review-42"}).status_code == 201
    assert client.post("/projects/p/admissions", json=admission(labelled_by=["bot"]), headers=HEADERS).status_code == 422


def test_unnamed_clauses_distinct_stable_and_identity_changes(harness, monkeypatch):
    p = assessment_project([constraint(), constraint()])
    app, client, _ = configure(harness, p)
    install_provider(app, monkeypatch)
    first = results(client, run(client)["executions"][0])
    second = results(client, run(client)["executions"][0])
    assert first[0]["clause"] != first[1]["clause"]
    assert [r["clause"] for r in first] == [r["clause"] for r in second]
    assert [r["oracle"] for r in first] == [r["oracle"] for r in second]
    original = expectation()
    assert judge_identity(original) != judge_identity(expectation(criteria="Changed"))
    assert judge_identity(original) != judge_identity(expectation(judge={"model":"another", "confidence_source":"self_rating"}))
    assert judge_identity(original) != judge_identity(expectation(judge={"model":"judge-v1", "confidence_source":"token_probability"}))


def test_single_agreement_and_unknown_composition_reject_preflight(harness):
    app, client, calls = configure(harness, assessment_project(expectations=[expectation(judge={
        "model":"judge-v1", "confidence_source":"agreement"})]))
    assert client.post(BASE, json={"suite":"s","environment":"test"}, headers=HEADERS).status_code == 422
    assert not calls


def test_failed_execution_never_assessed(harness, monkeypatch):
    app, client, _ = configure(harness, assessment_project())

    async def fail(*args):
        raise httpx.ConnectError("subject offline")
    monkeypatch.setattr(app.state.provider, "call", fail)
    record = run(client)["executions"][0]
    assert record["status"] == "infrastructure_failure"
    assert results(client, record) == []


def test_real_judge_http_and_restart(harness, monkeypatch, tmp_path):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, payload))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.path == "/subject":
                self.wfile.write(b'{"response":"42"}')
            else:
                self.wfile.write(b'{"verdict":"fail","confidence":0.8,"explanation":"Expected another value","assertions":2}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        monkeypatch.setenv("AQEF_PROVIDER_URLS", json.dumps({"subject-v1":base + "/subject", "judge-v1":base + "/judge"}))
        db = str(tmp_path / "assessment.db")
        app = create_app(db)
        client = TestClient(app)
        p = assessment_project(expectations=[expectation(judge={"model":"judge-v1", "confidence_source":"token_probability"})])
        assert client.post("/projects", json=p, headers=HEADERS).status_code == 201
        record = run(client)["executions"][0]
        rows = results(client, record)
        assert rows[0]["verdict"] == "fail" and rows[0]["assertions"] == 2
        assert [r[0] for r in requests] == ["/subject", "/judge"]
        assert requests[1][1]["confidence_source"] == "token_probability"
        admitted = client.post("/projects/p/admissions", json=admission(oracle=rows[0]["oracle"]), headers=HEADERS)
        assert admitted.status_code == 201
        reloaded = create_app(db)
        assert reloaded.state.storage.is_admitted("p", rows[0]["oracle"])
        assert results(TestClient(reloaded), record) == rows
        assert client.post("/projects/p/validators", json=custom_definition(), headers=HEADERS).status_code == 201
        assert create_app(db).state.storage.list_custom_validators("p") == [custom_definition()]
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_custom_binding_frozen_before_subject_and_no_silent_expected(harness, monkeypatch):
    p = assessment_project([constraint("exact", "response", None, dimension="functional")])
    app, client, _ = configure(harness, p)
    assert client.post("/projects/p/validators", json=custom_definition(), headers=HEADERS).status_code == 201

    async def call(model, payload, timeout):
        if model == "subject-v1":
            app.state.storage.create_custom_validator("p", custom_definition("v2"))
            return {"response":"approved"}
        return {"verdict":"pass", "confidence":.9, "assertions":1, "explanation":"good"}
    app.state.provider.urls["judge-v1"] = "http://judge.local"
    monkeypatch.setattr(app.state.provider, "call", call)
    row = results(client, run(client)["executions"][0])[0]
    assert row["verdict"] == "pass"


@pytest.mark.parametrize("expected", ["different", {"parameter":1}, [], 0, False])
def test_owner_o2_invalid_custom_expected_rejected_at_load_naming_clause(harness, expected):
    app, client, calls = harness
    p = assessment_project([constraint("exact@v1", "response", expected, dimension="functional", id="custom-status")])
    response = client.post("/projects", json=p, headers=HEADERS)
    assert response.status_code == 422
    assert "custom-status" in response.text
    assert not calls
    assert app.state.storage.get_project("p") is None


@pytest.mark.parametrize("expected", [None, {}])
def test_owner_o2_parameterless_custom_expected_forms(harness, monkeypatch, expected):
    app, client, _ = configure(harness, assessment_project([
        constraint("exact@v1", "response", expected, dimension="functional", id="custom-status")]))
    assert client.post("/projects/p/validators", json=custom_definition(), headers=HEADERS).status_code == 201
    install_provider(app, monkeypatch, subject="approved")
    assert results(client, run(client)["executions"][0])[0]["verdict"] == "pass"


@pytest.mark.parametrize("status,body", [(429, b'{}'), (302, b'{}'), (200, b'not json')])
def test_judge_http_unavailability(harness, monkeypatch, status, body):
    app, client, _ = configure(harness, assessment_project())
    app.state.provider.urls["judge-v1"] = "http://judge.local"
    from engine.providers import HTTPProvider
    real_client = httpx.AsyncClient
    calls = []

    def handle(request):
        payload = json.loads(request.content)
        calls.append(payload["model"])
        if payload["model"] == "subject-v1":
            return httpx.Response(200, json={"response":"answer"})
        return httpx.Response(status, content=body)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(app.state.provider, "call", HTTPProvider(app.state.provider.urls).call)
    row = results(client, run(client)["executions"][0])[0]
    assert row["disposition"] == "oracle_unavailable"
    assert row["verdict"] is None and row["confidence"] == "not_applicable"
    assert calls == ["subject-v1", "judge-v1"]


@pytest.mark.parametrize("policy", ["unknown", "and"])
def test_unknown_composition_rejects_before_subject(harness, policy):
    _, client, calls = harness
    response = client.post("/projects", json=assessment_project(policy=policy), headers=HEADERS)
    assert response.status_code == 422
    assert "validator_composition" in response.text
    assert not calls


def test_recorded_duration_and_usage_checked_cheapest_first(harness, monkeypatch):
    checks = [constraint("schema", expected="json", id="schema"),
              constraint("cost", "artifacts.usage", 12, id="cost"),
              constraint("latency", "duration_ms", "30s", id="latency")]
    app, client, _ = configure(harness, assessment_project(checks))
    install_provider(app, monkeypatch)
    rows = results(client, run(client)["executions"][0])
    assert [r["clause"] for r in rows] == ["cost", "latency", "schema", "quality"]
    assert all(r["verdict"] == "pass" for r in rows)
    assert rows[0]["supporting_evidence"]["check"]["observed"] == 12


def test_validator_crash_blocks_judge(harness, monkeypatch):
    app, client, _ = configure(harness, assessment_project([constraint()]))
    calls = install_provider(app, monkeypatch)

    def crash(*args):
        raise RuntimeError("broken check")
    monkeypatch.setattr("engine.assessment.check_builtin", crash)
    row = results(client, run(client)["executions"][0])[0]
    assert row["disposition"] == "oracle_unavailable" and row["verdict"] is None
    assert "broken check" in row["supporting_evidence"]["error"]
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [{"confidence":None}, {"confidence":True}, {"confidence":.8},
                                    {"disposition":"inconclusive"}, {"verdict":None}])
def test_result_model_prohibits_inconsistent_validator_shapes(changes):
    row = {"id":"r", "execution":"e", "clause":"c", "oracle_type":"validator", "oracle":"schema@1",
           "verdict":"pass", "confidence":"not_applicable", "disposition":"actionable",
           "supporting_evidence":{}, "recorded_at":"2026-10-24T00:00:00Z"}
    with pytest.raises(ValueError):
        Result.model_validate(row | changes)
