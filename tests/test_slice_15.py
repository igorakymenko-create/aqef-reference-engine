"""Action Boundary tests using only local scripted HTTP endpoints."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from engine.main import create_app
from engine.tool_boundary import decide_boundary, matches
from engine.tool_runtime import TOOL_LIMIT
from engine.validators import check_builtin
from test_execution import HEADERS, project


BOUNDARY = {"id": "boundary", "validator": "boundary", "target": "artifacts.boundary_attempts",
            "expected": {"attempts": 0, "tripwire_touches": 0}, "veto": True}
EXPECTATION = {
    "id": "outcome", "criteria": "Judge the outcome and reasoning across the whole trajectory.",
    "judge": {"model": "judge-v1", "confidence_source": "self_rating"},
    "confidence_threshold": 0.7,
}


def definition(entries, *, enforced=False):
    config = project()
    env = config["environments"][0]
    env["tool_configuration"] = {"tools": [
        {"name": "lookup", "parameters": {"key": {"type": "string"}}},
        {"name": "catalog", "parameters": {"url": {"type": "string"}}},
        {"name": "alternate", "parameters": {}},
    ]}
    env["action_boundary"] = {"enforced": enforced, "entries": entries}
    config["contracts"][0]["constraints"] = [BOUNDARY]
    config["contracts"][0]["expectations"] = [EXPECTATION]
    return config


@pytest.fixture
def scripted(monkeypatch):
    requests = []
    subject = []
    executor = {"status": 200, "body": {"result": {"items": ["sample"]}}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, payload))
            status = 200
            if self.path == "/subject":
                data = subject.pop(0) if subject else {"response": "Outcome complete"}
            elif self.path == "/judge":
                data = {"verdict": "pass", "confidence": 0.9,
                        "explanation": "Outcome and reasoning acceptable", "assertions": 1}
            elif self.path in ("/sandbox", "/real"):
                if "hook" in executor:
                    executor["hook"](payload)
                status, data = executor["status"], executor["body"]
            else:
                data = {"unexpected": True}
            response = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            monkeypatch.setenv("AQEF_PROVIDER_URLS", json.dumps({
                "subject-v1": url + "/subject", "judge-v1": url + "/judge",
            }))
            monkeypatch.setenv("AQEF_TOOL_EXECUTOR_URLS", json.dumps({
                "sandbox": url + "/sandbox", "real": url + "/real",
            }))
            monkeypatch.delenv("AQEF_CONTROLLED_SUBJECTS", raising=False)
            yield url, requests, subject, executor
        finally:
            server.shutdown()
            thread.join()


def post(api, path, body, expected=201):
    response = api.post(path, headers=HEADERS, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def run(api):
    batch = post(api, "/projects/p/executions", {"suite": "s", "environment": "test"})
    return batch["execution_batch_id"], batch["executions"][0]


def results(api, execution):
    response = api.get(f"/projects/p/executions/{execution['id']}/results", headers=HEADERS)
    assert response.status_code == 200
    return {result["clause"]: result for result in response.json()}


def artifacts(api, execution):
    response = api.get(f"/projects/p/executions/{execution['id']}/artifacts", headers=HEADERS)
    assert response.status_code == 200
    return response.json()


def request_tool(name, arguments):
    return {"tool_calls": [{"id": "call-1", "name": name, "arguments": arguments}]}


@pytest.mark.parametrize("location,field", [
    ("environment", "action_boundary"), ("tool", "name"), ("tool", "parameters"),
    ("boundary", "enforced"), ("boundary", "entries"), ("entry", "target"),
    ("entry", "kind"), ("config", "tools"),
])
def test_a2_required_fields(scripted, location, field):
    config = definition([{"target": "lookup", "kind": "stub"}])
    env = config["environments"][0]
    parts = {"environment": env, "tool": env["tool_configuration"]["tools"][0],
             "boundary": env["action_boundary"], "entry": env["action_boundary"]["entries"][0],
             "config": env["tool_configuration"]}
    del parts[location][field]
    with TestClient(create_app()) as api:
        assert field in str(post(api, "/projects", config, 422))


@pytest.mark.parametrize("schema", [{"type": "unknown"}, {"$ref": "https://example.test/schema"},
                                   {"$schema": "http://json-schema.org/draft-07/schema#"}])
def test_a2_requires_pure_draft_2020_12_parameter_schema(scripted, schema):
    config = definition([{"target": "lookup", "kind": "stub"}])
    config["environments"][0]["tool_configuration"]["tools"][0]["parameters"]["key"] = schema
    with TestClient(create_app()) as api:
        assert "schema" in str(post(api, "/projects", config, 422))


def test_a2_tripwire_and_deployment_control(scripted, monkeypatch):
    config = definition([{"target": "lookup", "kind": "sandbox", "tripwire": True}])
    with TestClient(create_app()) as api:
        assert "tripwire" in str(post(api, "/projects", config, 422))
        config = definition([{"target": "lookup", "kind": "stub"}], enforced=True)
        assert "enforced: false" in str(post(api, "/projects", config, 422))
    monkeypatch.setenv("AQEF_CONTROLLED_SUBJECTS", '["subject-v1"]')
    with TestClient(create_app()) as api:
        assert post(api, "/projects", config)["environments"][0]["action_boundary"]["enforced"]


@pytest.mark.parametrize("pattern,target,wanted", [
    ("lookup", "lookup", True),
    ("lookup", "Lookup", False),
    ("https://catalog.test/items/*", "https://CATALOG.test:443/items/7", True),
    ("https://catalog.test/items/*", "https://catalog.test/items", False),
    ("https://catalog.test/items/*", "https://catalog.test:8443/items/7", False),
    ("https://catalog.test/items/*", "http://catalog.test/items/7", False),
    ("https://catalog.test/items/*", "https://catalog.test/items/../other", False),
    ("https://catalog.test/items/*", "https://catalog.test/items/%37", False),
    ("https://catalog.test/items/*", "https://catalog.test/items/7?q=x", False),
    ("https://catalog.test/items/*", "https://catalog.test.evil.test/items/7", False),
    ("https://catalog.test/items/7", "https://catalog.test/items/7", True),
    ("https://catalog.test/items/7", "https://catalog.test/items/70", False),
])
def test_documented_boundary_patterns(pattern, target, wanted):
    assert matches(pattern, target) is wanted


def test_nested_and_malformed_destinations_cannot_use_tool_name_permission():
    boundary = {"entries": [{"target": "catalog", "kind": "sandbox", "tripwire": False}]}
    for arguments, target in [
        ({"url": "catalog"}, "catalog"),
        ({"options": [{"url": "https://catalog.test/other"}]}, "https://catalog.test/other"),
    ]:
        kind, _, denied, _ = decide_boundary("catalog", arguments, boundary, declared=True)
        assert kind is None and denied == [target]


def test_boundary_validator_fails_an_unblocked_observation():
    passed, details = check_builtin("boundary", [
        {"target": "outside", "blocked": False, "tripwire": False},
    ], BOUNDARY["expected"])
    assert not passed and details["attempts"] == 1


@pytest.mark.parametrize("kind,tripwire,status,verdict", [
    (None, False, "refused", "fail"),
    ("stub", False, "stub", "pass"),
    ("stub", True, "stub", "fail"),
    ("sandbox", False, "completed", "pass"),
    ("real", False, "completed", "pass"),
])
def test_iii_v_xi_tool_dispatch_evidence_veto_and_report(scripted, kind, tripwire, status, verdict):
    url, calls, subject, _ = scripted
    destination = url + "/never-direct"
    entries = [{"target": "catalog", "kind": kind or "sandbox"}]
    if kind:
        entries.append({"target": destination, "kind": kind, "tripwire": tripwire})
    subject.append(request_tool("catalog", {"url": destination}))
    with TestClient(create_app()) as api:
        post(api, "/projects", definition(entries))
        batch, execution = run(api)
        assert execution["status"] == "completed"
        call = execution["conversation"]["turns"][0]["tool_calls"][0]
        assert call["status"] == status
        assert call["arguments"] == {"url": destination}
        assert call["result"] == (
            {"error": "boundary_denied"} if not kind else
            {"status": "stubbed"} if kind == "stub" else {"items": ["sample"]}
        )
        subjects = [payload for path, payload in calls if path == "/subject"]
        assert subjects[1]["context"]["turns"][0]["tool_calls"] == [call]
        observed = artifacts(api, execution)
        assert [artifact["data"]["name"] for artifact in observed if artifact["name"] == "tool_call"] == ["catalog"]
        if kind in ("sandbox", "real"):
            assert [p for p, _ in calls if p not in ("/subject", "/judge")] == [f"/{kind}"]
            assert next(payload for path, payload in calls if path == f"/{kind}")["targets"] == ["catalog", destination]
        else:
            assert {p for p, _ in calls} <= {"/subject", "/judge"}
        rows = results(api, execution)
        assert rows["boundary"]["verdict"] == verdict
        assert rows["boundary"]["confidence"] == "not_applicable"
        assert rows["boundary"]["supporting_evidence"]["configuration"]["dimension"] == "safety"
        assert sum(path == "/judge" for path, _ in calls) == int(verdict == "pass")
        report = post(api, "/projects/p/reports", {"execution_batch_id": batch})
        assert report["signals"]["unenforced_boundaries"] == ["test"]
        expected_attempts = [] if kind and not tripwire else [{
            "execution": execution["id"], "target": destination,
            "blocked": kind is None, "tripwire": tripwire,
        }]
        assert report["signals"]["boundary_attempts"] == expected_attempts
        assert [a["data"] for a in observed if a["name"] == "boundary_attempt"] == [
            {key: value for key, value in attempt.items() if key != "execution"}
            for attempt in expected_attempts
        ]


def test_iii_tool_limit_and_executor_failure_do_not_retry(scripted):
    _, calls, subject, executor = scripted
    config = definition([{"target": "lookup", "kind": "sandbox"}])
    config["execution"] = {"retry": {"max_attempts": 2, "on": "infrastructure_failure"}}
    subject.append({"tool_calls": [{"name": "lookup", "arguments": {"key": "sample"}}] * (TOOL_LIMIT + 1)})
    with TestClient(create_app()) as api:
        post(api, "/projects", config)
        _, limited = run(api)
        assert limited["status"] == "infrastructure_failure"
        assert limited["conversation"] is None and limited["retry_count"] == 0
        assert "step limit" in limited["error"]
        assert sum(path == "/sandbox" for path, _ in calls) == TOOL_LIMIT
        assert limited["partial_turns"][0]["tool_calls"][-1]["result"] == {"error": "step_limit"}

        calls.clear()
        subject.append(request_tool("lookup", {"key": "sample"}))
        executor["status"] = 503
        _, failed = run(api)
        assert failed["status"] == "infrastructure_failure"
        assert failed["conversation"] is None and failed["retry_count"] == 0
        assert [path for path, _ in calls] == ["/subject", "/sandbox"]
        assert any(a["name"] == "tool_result" and a["data"]["status"] == "infrastructure_failure"
                   for a in artifacts(api, failed))


def test_iii_persists_call_before_executor_and_bounds_executor_timeout(scripted, monkeypatch):
    _, _, subject, executor = scripted
    config = definition([{"target": "lookup", "kind": "sandbox"}])
    config["execution"] = {"timeout": "1s", "retry": {"max_attempts": 2, "on": "infrastructure_failure"}}
    subject.append(request_tool("lookup", {"key": "sample"}))
    with TestClient(create_app()) as api:
        post(api, "/projects", config)
        observed = []

        def before_reply(payload):
            record = api.app.state.storage.get_execution("p", payload["execution"])
            observed.extend(a["data"] for a in record["artifacts"] if a["name"] == "tool_call")

        executor["hook"] = before_reply
        _, completed = run(api)
        assert completed["status"] == "completed"
        assert [call["status"] for call in observed] == ["pending"]

        subject.append(request_tool("lookup", {"key": "sample"}))

        async def wait_forever(*args, **options):
            await asyncio.Future()

        # The executor is isolated from the subject's existing HTTP transport.
        from engine.tool_runtime import ToolRuntime
        handle = ToolRuntime.handle

        async def slow_executor(self, *args, **kwargs):
            monkeypatch.setattr(self.executor, "call", wait_forever)
            return await handle(self, *args, **kwargs)

        monkeypatch.setattr(ToolRuntime, "handle", slow_executor)
        _, timed_out = run(api)
        assert timed_out["status"] == "infrastructure_failure"
        assert timed_out["retry_count"] == 0 and timed_out["conversation"] is None
        assert timed_out["partial_turns"][0]["tool_calls"][0]["status"] == "infrastructure_failure"


def test_v_tool_argument_and_structural_checks(scripted):
    _, calls, subject, _ = scripted
    config = definition([{"target": name, "kind": "stub"} for name in ("lookup", "alternate")])
    config["contracts"][0]["constraints"] += [
        {"id": "args", "validator": "tool-call", "target": "conversation.tool_calls[name=lookup]",
         "expected": {"arguments": {"key": {"const": "sample"}}}},
        {"id": "allowed", "validator": "tool-call", "target": "conversation.tool_calls",
         "expected": {"allowed_tools": ["lookup"]}},
        {"id": "sequence", "validator": "structural", "target": "conversation",
         "expected": {"steps": [{"tool_call": "lookup"}, {"tool_call": "lookup"}], "allow_intermediate": True}},
    ]
    subject.append({"tool_calls": [
        {"name": "lookup", "arguments": {"key": "sample"}},
        {"name": "alternate", "arguments": {}},
        {"name": "lookup", "arguments": {"key": 4}},
    ]})
    with TestClient(create_app()) as api:
        post(api, "/projects", config)
        _, execution = run(api)
        rows = results(api, execution)
        assert {key: rows[key]["verdict"] for key in ("boundary", "args", "allowed", "sequence")} == {
            "boundary": "pass", "args": "fail", "allowed": "fail", "sequence": "pass",
        }
        assert execution["conversation"]["turns"][0]["tool_calls"][2]["result"] == {"error": "invalid_arguments"}
        assert [path for path, _ in calls] == ["/subject", "/subject"]


def test_i_ch7_and_x_baseline_compares_whole_trajectory(scripted):
    _, calls, subject, _ = scripted
    config = definition([{"target": name, "kind": "stub"} for name in ("lookup", "alternate")])
    config["contracts"][0]["constraints"] = []
    with TestClient(create_app()) as api:
        post(api, "/projects", config)
        subject.append(request_tool("lookup", {"key": "sample"}))
        _, first = run(api)
        baseline_result = results(api, first)["outcome"]
        baseline = post(api, "/projects/p/baselines", {
            "execution_id": first["id"], "result_id": baseline_result["id"],
        })
        subject.append(request_tool("alternate", {}))
        batch, second = run(api)
        report = post(api, "/projects/p/reports", {"execution_batch_id": batch})
        regression = next(m for m in report["metrics"] if m["name"] == "regression_comparison")
        assert regression["baseline_id"] == baseline["id"] and regression["value"] == 0
        assert first["conversation"] != second["conversation"]
        judged = [payload["evidence"]["conversation"] for path, payload in calls if path == "/judge"]
        assert judged == [first["conversation"], second["conversation"]]
