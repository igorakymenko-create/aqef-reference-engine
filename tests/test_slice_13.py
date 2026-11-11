"""Independent Volume XIV client checks against the engine's live REST API."""

import ast
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from threading import Thread
import time

import httpx
import pytest
import uvicorn
import yaml

from aqef_client import APIError, Client
from aqef_client._commands import COMMANDS
from engine.main import create_app
from test_execution import project

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "slice13-local-admin-secret"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class Subject(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = b'{"response":"hello"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextmanager
def serve_engine(db):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(
            create_app(str(db)), log_level="warning", lifespan="off",
        ))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline and thread.is_alive():
                time.sleep(0.01)
            assert server.started
            yield url
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


@pytest.fixture(scope="session")
def live(tmp_path_factory):
    folder = tmp_path_factory.mktemp("slice13")
    with ThreadingHTTPServer(("127.0.0.1", 0), Subject) as provider:
        thread = Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            with ExitStack() as stack:
                with pytest.MonkeyPatch.context() as env:
                    env.setenv("AQEF_ADMIN_TOKEN", TOKEN)
                    env.setenv("AQEF_PROVIDER_URLS", json.dumps({
                        "subject-v1": f"http://127.0.0.1:{provider.server_port}/subject",
                    }))
                    urls = tuple(stack.enter_context(serve_engine(folder / f"{i}.db"))
                                 for i in range(2))
                yield urls
        finally:
            provider.shutdown()
            thread.join()


def definition(name, *, passing=True):
    data = project()
    data["name"] = name
    data["contracts"][0]["constraints"] = [{
        "id": "shape", "validator": "schema", "target": "response",
        "expected": {"type": "string" if passing else "integer"},
    }]
    data["quality_gates"] = [{
        "name": "functional", "aggregate": "functional", "threshold": 1,
        "on_failure": "block_release",
    }]
    data["environments"].append(data["environments"][0] | {"name": "spare"})
    data["suites"][0]["scenarios"].append({"name": "b", "prompt": {"template": "Hello"}})
    data["datasets"] = [{"name": "d", "version": "v1", "source": "static",
                         "rows": [{"id": "r", "variables": {"who": "world"}}]}]
    return data


def route_bodies(data):
    environment = data["environments"][0]
    scenario = data["suites"][0]["scenarios"][0]
    contract = data["contracts"][0]
    gate = data["quality_gates"][0]
    dataset = data["datasets"][0]
    batch = {"execution_batch_id": "missing"}
    scope = {"suites": ["s"], "environments": ["test"]}
    return {
        "create_team": {"id": "team", "name": "Team"},
        "create_role": {"name": "triage", "permissions": ["read"]},
        "create_principal": {"id": "triager", "name": "Triager", "kind": "person"},
        "create_project": data | {"name": "created-by-operation"},
        "update_project": data,
        "create_environment": environment | {"name": "new"},
        "update_environment": environment,
        "create_suite": {"name": "new", "scenarios": [scenario]},
        "create_scenario": scenario | {"name": "new"},
        "update_scenario": scenario | {"name": "b"},
        "create_contract": contract | {"name": "new"},
        "update_contract": contract,
        "create_dataset": dataset | {"name": "new"},
        "create_dataset_version": dataset | {"version": "v2"},
        "create_quality_gate": gate | {"name": "new"},
        "update_quality_gate": gate,
        "trigger_execution": {"suite": "missing", "environment": "test"},
        "record_admission": {
            "oracle": "judge", "reference_set": "set@1", "items": 1,
            "verdict_distribution": {"pass": 1}, "raw_agreement": 1,
            "measure": "kappa", "chance_corrected_agreement": "not_computed",
            "threshold": 0.9, "admitted": False, "labelled_by": ["admin"],
        },
        "register_validator": {"name": "equals-hi", "version": "1",
                               "rule": {"operation": "equals", "expected": "hi"}},
        "check_gates": batch,
        "capture_snapshot": scope,
        "generate_report": batch,
        "override_gate": batch | {"gate_result_id": "missing", "justification": "Review"},
        "approve_baseline": {"execution_id": "missing", "result_id": "missing"},
        "approve_release_policy": scope | {"service_accounts": ["runner"]},
        "record_release": batch | {"report_id": "missing", "snapshot_id": "missing",
                                   "decision": "rejected"},
        "review_result": {"verdict": "pass", "supporting_evidence": "reviewed"},
        "reassess_result": {"oracle": "missing"},
        "confirm_seeded_control": {"confirmed": True, "supporting_evidence": "observed"},
        "invalidate_seeded_control": {"reason": "observed"},
        "record_requalification": {"oracle": "missing", "defect_class": "example",
                                   "controls": ["missing"]},
    }


def comparable(data):
    """Normalize server-generated UUIDs and timestamps only."""
    if isinstance(data, dict):
        return {key: comparable(value) for key, value in data.items()}
    if isinstance(data, list):
        return [comparable(value) for value in data]
    if isinstance(data, str):
        if re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", data):
            return "<uuid>"
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", data):
            return "<timestamp>"
    return data


@pytest.mark.parametrize("operation", COMMANDS, ids=[row[1] for row in COMMANDS])
def test_xiv_sdk_matches_raw_live_api(live, operation):
    _, name, verb, template, path_keys, query_keys, header_keys, has_body = operation
    data = definition(f"parity-{name}")
    paths = {
        "project": data["name"], "env": "spare" if name == "delete_environment" else "test",
        "suite": "s", "scenario": "b", "contract": "c", "dataset": "d", "gate": "functional",
        "execution": "missing", "result": "missing", "policy": "missing", "key": "missing",
        "evaluation": "missing",
    }
    values = {"offset": 0, "limit": 5, "version": "v1", "retain_history": False,
              "x_approved_by": "admin", "x_external_review_ref": "slice13-review",
              "suite": "s", "environment": "test", "status": "completed",
              "date_from": "2026-01-01T00:00:00Z", "date_to": "2026-12-01T00:00:00Z",
              "oracle_type": "validator", "verdict": "pass", "oracle": "judge",
              "action": "contract_define", "principal_id": "admin"}
    kwargs = {key: paths[key] for key in path_keys}
    kwargs.update({arg: values[arg] for _, arg in query_keys + header_keys})
    raw_headers = HEADERS | {key: values[arg] for key, arg in header_keys}
    raw_options = {"params": {key: values[arg] for key, arg in query_keys},
                   "headers": raw_headers}
    if has_body:
        kwargs["body"] = raw_options["json"] = route_bodies(data)[name]

    for url in live:
        if "project" in path_keys:
            seeded = httpx.post(url + "/projects", json=data, headers=HEADERS)
            assert seeded.status_code == 201, seeded.text
        if name == "approve_release_policy":
            seeded = httpx.post(url + "/principals", headers=HEADERS, json={
                "id": "runner", "kind": "service_account", "name": "Runner",
                "owner_person_id": "admin",
            })
            assert seeded.status_code == 201, seeded.text
    raw = httpx.request(verb, live[0] + template.format(**paths), **raw_options)
    assert raw.status_code < 500, raw.text
    with Client(live[1], TOKEN) as sdk:
        if raw.is_error:
            with pytest.raises(APIError) as caught:
                getattr(sdk, name)(**kwargs)
            assert caught.value.status_code == raw.status_code
            assert caught.value.body == raw.content
            assert TOKEN not in str(caught.value)
        else:
            actual = getattr(sdk, name)(**kwargs)
            assert actual.status_code == raw.status_code
            if raw.content:
                assert comparable(actual.json()) == comparable(raw.json())
            else:
                assert actual.content == b""


def test_xiv_openapi_inventory_and_client_engine_boundary():
    schema = json.loads((ROOT / "docs/OPENAPI.json").read_text(encoding="utf-8"))
    operations = {(verb.upper(), path) for path, routes in schema["paths"].items()
                  for verb in routes}
    assert len(COMMANDS) == len(operations)
    assert {(verb, path) for _, _, verb, path, *_ in COMMANDS} == operations
    for _, name, verb, path, *_ in COMMANDS:
        assert getattr(Client, name).__doc__ == f"{verb} {path}."
    client = ROOT / "client"
    for file in [*(client / "aqef_client").rglob("*.py"), *(client / "tools").rglob("*.py")]:
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if isinstance(node, ast.Call) and node.args:
                function = getattr(node.func, "id", getattr(node.func, "attr", None))
                argument = node.args[0]
                if function in ("__import__", "import_module") and isinstance(argument, ast.Constant):
                    names = [str(argument.value)]
            assert not any(name.split(".")[0] == "engine" for name in names), file


@pytest.fixture
def cli(live):
    def run(*args, url=None, token=TOKEN):
        environment = os.environ | {
            "AQEF_URL": url or live[0], "AQEF_TOKEN": token,
        }
        # Run the installed console script when available. Source-only checkouts
        # can use the same main entry point without a build-time network dependency.
        script = os.environ.get("AQEF_TEST_CLI") or shutil.which("aqef")
        if script:
            command = [script]
        else:
            command = [sys.executable, "-m", "aqef_client.cli"]
            environment["PYTHONPATH"] = str(ROOT / "client")
        return subprocess.run([*command, *map(str, args)], env=environment,
                              capture_output=True, timeout=25)
    return run


def write_file(tmp_path, name, data, *, yaml_file=False):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data) if yaml_file else json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("passing", [True, False])
def test_xiv_cli_live_loop_and_blocking_exit(live, cli, tmp_path, passing):
    name = f"cli-loop-{passing}"
    file = write_file(tmp_path, "project.yaml", definition(name, passing=passing), yaml_file=True)
    loaded = cli("--json", "project", "load", file)
    assert loaded.returncode == 0, loaded.stderr
    batch = cli("execution", "run", "--project", name, "--suite", "s",
                "--environment", "test", "--wait", "--json")
    assert batch.returncode == 0, batch.stderr
    run = json.loads(batch.stdout)
    execution = run["executions"][0]["id"]
    path = f"/projects/{name}/executions/{execution}/results"
    results = cli("result", "list", "--project", name, "--execution", execution, "--json")
    assert results.returncode == 0, results.stderr
    assert results.stdout == httpx.get(live[0] + path, headers=HEADERS).content
    request = write_file(tmp_path, "batch.json", {"execution_batch_id": run["execution_batch_id"]})
    checked = cli("gates", "check", "--project", name, request, "--json")
    assert checked.returncode == (0 if passing else 1), checked.stderr
    gate = json.loads(checked.stdout)["gates"]["functional"]
    assert gate["status"] == ("pass" if passing else "fail")
    if not passing:
        override = write_file(tmp_path, "override.json", {
            "execution_batch_id": run["execution_batch_id"], "gate_result_id": gate["id"],
            "justification": "Explicit decision",
        })
        result = cli("gate", "override", "--project", name, "--gate", "functional", override)
        assert result.returncode == 0, result.stderr
        assert b"GateResult overridden" in result.stdout
        report = cli("report", "generate", "--project", name, request)
        assert report.returncode == 0, report.stderr
        assert b"Gate functional: overridden" in report.stdout
        assert b'"status": "fail"' in report.stdout


RESOURCES = {}
for entry in COMMANDS:
    RESOURCES.setdefault(entry[0].split()[0], entry)


@pytest.mark.parametrize("operation", RESOURCES.values(), ids=list(RESOURCES))
def test_xiv_cli_propagates_api_error_per_resource(live, cli, tmp_path, operation):
    command, _, verb, template, keys, query, _, has_body = operation
    args = command.split()
    for key in keys:
        args.extend(("--" + key.replace("_", "-"), "missing"))
    options = {}
    if has_body:
        args.append(write_file(tmp_path, "invalid.json", {}))
        options["json"] = {}
    if ("limit", "limit") in query:
        args.extend(("--limit", "0"))
        options["params"] = {"limit": 0}
    token = "invalid" if command == "system health" else TOKEN
    raw = httpx.request(verb, live[0] + template.format(**dict.fromkeys(keys, "missing")),
                        headers={"Authorization": f"Bearer {token}"}, **options)
    assert raw.is_client_error, raw.text
    actual = cli(*args, "--json", token=token)
    assert actual.returncode == 2
    assert actual.stdout == b""
    assert actual.stderr == f"HTTP {raw.status_code}\n".encode() + raw.content


def test_xiv_cli_keeps_parsed_body_and_reports_usage_transport_and_timeout(live, cli, tmp_path):
    definition_file = write_file(tmp_path, "number.yaml", definition("numeric-version"), yaml_file=True)
    parsed = yaml.safe_load(definition_file.read_text())
    parsed["datasets"][0]["version"] = 1.0
    definition_file.write_text(yaml.safe_dump(parsed), encoding="utf-8")
    raw = httpx.post(live[0] + "/projects", headers=HEADERS, json=parsed)
    assert raw.status_code == 422
    result = cli("project", "load", definition_file, "--json")
    assert result.returncode == 2
    assert result.stderr == b"HTTP 422\n" + raw.content
    assert cli("project", "get").returncode == 64
    assert cli("project", "list", "--timeout", "inf").returncode == 64
    assert cli("project", "list", "--token", "fake").returncode == 64
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        result = cli("system", "health", url=f"http://127.0.0.1:{unavailable.getsockname()[1]}")
        assert result.returncode == 3
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        result = cli("execution", "run", "--project", "p", "--suite", "s", "--environment", "test",
                     "--wait", "--timeout", "0.1", url=f"http://127.0.0.1:{silent.getsockname()[1]}")
        assert result.returncode == 3
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN, encoding="utf-8")
    result = cli("system", "health", "--token-file", token_file, "--json", token="invalid")
    assert result.returncode == 0
    assert result.stdout == httpx.get(live[0] + "/healthz", headers=HEADERS).content
    assert TOKEN.encode() not in result.stdout + result.stderr


def test_c4_c5_governed_headers_reach_engine_through_sdk_and_cli(live, cli, tmp_path):
    name = "governed-client"
    service_token = "slice13-local-service-secret"
    with Client(live[0], TOKEN) as admin:
        admin.create_role({"name": "contract-editor", "permissions": [
            "project_create", "contract_define",
        ]})
        admin.create_principal({
            "id": "contract-runner", "kind": "service_account", "name": "Contract runner",
            "owner_person_id": "admin", "roles": ["contract-editor"], "token": service_token,
        })
        with Client(live[0], service_token) as sdk:
            with pytest.raises(APIError) as error:
                sdk.create_project(definition(name))
            assert error.value.status_code == 422
            assert sdk.create_project(
                definition(name), x_approved_by="admin", x_external_review_ref="review/sdk",
            ).status_code == 201
        file = write_file(tmp_path, "governed.json", definition(name + "-cli"))
        loaded = cli("project", "load", file, "--x-approved-by", "admin",
                     "--x-external-review-ref", "review/cli", token=service_token)
        assert loaded.returncode == 0, loaded.stderr
        for project_name, reference in [(name, "review/sdk"), (name + "-cli", "review/cli")]:
            approvals = admin.list_approvals(project_name).json()
            assert len(approvals) == 1
            assert approvals[0]["approved_by"] == "admin"
            assert approvals[0]["external_review_reference"] == reference
