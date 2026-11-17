"""Live engine and external examples, Volume XVI and Appendix C §C.7."""

from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import socket
from threading import Thread
import time

import pytest
import uvicorn
from fastapi import Request

from aqef_client import APIError, Client
from examples.plugins.providers import app
from test_slice_13 import TOKEN, Subject, definition, serve_engine


@app.middleware("http")
async def no_engine_credentials(request: Request, call_next):
    assert "authorization" not in request.headers
    assert TOKEN.encode() not in await request.body()
    return await call_next(request)


@contextmanager
def serve_plugins():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=1))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            yield f"http://127.0.0.1:{listener.getsockname()[1]}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)


@pytest.fixture(scope="module")
def plugins(tmp_path_factory):
    with serve_plugins() as root, ThreadingHTTPServer(("127.0.0.1", 0), Subject) as subject:
        thread = Thread(target=subject.serve_forever, daemon=True)
        thread.start()
        urls = {kind: f"{root}/{kind}" for kind in ("validator", "judge", "dataset", "report")}
        try:
            with pytest.MonkeyPatch.context() as env:
                env.setenv("AQEF_ADMIN_TOKEN", TOKEN)
                env.setenv("AQEF_PLUGIN_URLS", json.dumps(urls))
                env.setenv("AQEF_PROVIDER_URLS", json.dumps({"subject-v1": f"http://127.0.0.1:{subject.server_port}/subject"}))
                with serve_engine(tmp_path_factory.mktemp("slice17") / "engine.db") as url, Client(url, TOKEN) as client:
                    yield client, urls | {"engine": url}
        finally:
            subject.shutdown()
            thread.join()


def register(plugins, kind, name, **options):
    client, urls = plugins
    return client.register_plugin({"type": kind, "name": name, "version": "1",
                                   "endpoint": urls[kind], "configuration": {"oracle": f"{name}@1", **options}}).json()


def trigger(client, name):
    run = client.trigger_execution(name, {"suite": "s", "environment": "test"}).json()
    results = client.list_results(name, run["executions"][0]["id"]).json()
    assert TOKEN not in json.dumps(results)
    return run, results


@pytest.mark.parametrize("mode", ["extra", "crash", "timeout", "nonjson", "malformed", "confidence"])
def test_xvi_validator_invocation_scope_and_c7_failure(plugins, mode):
    client, _ = plugins
    name = f"validator-{mode}"
    registered = register(plugins, "validator", name, mode=mode)
    assert registered["repeatability_check"] == {"runs": 2, "output_matched": True}
    config = definition(name)
    config["contracts"][0]["constraints"][0].update(validator=f"plugin:{name}@1", dimension="functional")
    config["execution"] = {"timeout": "PT0.5S"}
    client.create_project(config)
    _, results = trigger(client, name)
    result, = results
    assert result["oracle"] == f"{name}@1"
    if mode == "extra":
        assert result["verdict"] == "pass"
        assert result["supporting_evidence"]["ignored_reply_fields"] == ["mutate"]
    else:
        assert result["verdict"] is None and result["disposition"] == "oracle_unavailable"


@pytest.mark.parametrize("mode", ["valid", "confidence", "criteria"])
def test_xvi_judge_criteria_and_confidence(plugins, mode):
    client, _ = plugins
    name = f"judge-{mode}"
    register(plugins, "judge", name, mode=mode, confidence=0.4)
    config = definition(name)
    config["contracts"][0]["expectations"] = [{"id": "meaning", "criteria": "Greet politely",
        "judge": {"model": "independent", "confidence_source": "self_rating", "plugin": f"{name}@1"},
        "confidence_threshold": 0.8}]
    client.create_project(config)
    _, results = trigger(client, name)
    result = next(result for result in results if result["oracle_type"] == "judge")
    assert result["oracle"] == f"{name}@1"
    assert result["disposition"] == ("inconclusive" if mode == "valid" else "oracle_unavailable")


def test_xvi_registry_repeatability_and_typed_bindings(plugins):
    client, _ = plugins
    with pytest.raises(APIError) as rejected:
        register(plugins, "validator", "variable", mode="variable")
    assert rejected.value.status_code == 422
    register(plugins, "judge", "wrong")
    for ref in ("unknown@1", "wrong@1"):
        config = definition("bad-binding")
        config["contracts"][0]["constraints"][0].update(validator=f"plugin:{ref}", dimension="functional")
        with pytest.raises(APIError) as rejected:
            client.create_project(config)
        assert rejected.value.status_code == 422
        assert b"shape" in rejected.value.body


def test_xvi_dataset_version_and_metric_result_links(plugins):
    client, _ = plugins
    register(plugins, "dataset", "rows")
    register(plugins, "report", "metric")
    register(plugins, "report", "no-links", missing=True)
    config = definition("plugin-consumers")
    config["datasets"] = [{"source": "plugin", "name": "rows", "version": "1", "plugin": "rows@1"}]
    scenario = config["suites"][0]["scenarios"][0]
    scenario.pop("variables")
    scenario["dataset"] = "rows@1"
    saved = client.create_project(config).json()
    assert saved["datasets"][0]["rows"][0]["id"] == "one"
    run, results = trigger(client, "plugin-consumers")
    assert run["executions"][0]["dataset"] == "rows@1"
    assert run["executions"][0]["row_id"] == "one"
    for ref in ("metric@1", "no-links@1"):
        request = {"execution_batch_id": run["execution_batch_id"], "plugin": ref}
        if ref == "metric@1":
            metric = client.generate_metric("plugin-consumers", request).json()
            assert metric["plugin"] == ref and results[0]["id"] in metric["result_ids"]
            assert client.get_metric("plugin-consumers", metric["id"]).json() == metric
        else:
            with pytest.raises(APIError) as rejected:
                client.generate_metric("plugin-consumers", request)
            assert rejected.value.status_code == 502


def test_xvi_invalid_dataset_rows_leave_no_version(plugins):
    client, _ = plugins
    register(plugins, "dataset", "broken-rows", mode="invalid")
    client.create_project(definition("broken-dataset"))
    before = client.list_datasets("broken-dataset").json()
    with pytest.raises(APIError) as rejected:
        client.create_dataset("broken-dataset", {"source": "plugin", "name": "bad", "version": "1",
                                                "plugin": "broken-rows@1"})
    assert rejected.value.status_code == 502
    assert client.list_datasets("broken-dataset").json() == before


def test_xvi_judge_dataset_and_metric_bindings_reject_wrong_type(plugins):
    client, _ = plugins
    register(plugins, "report", "wrong-kind")
    config = definition("bad-judge")
    config["contracts"][0]["expectations"] = [{"id": "meaning", "criteria": "Greet politely",
        "judge": {"model": "independent", "confidence_source": "self_rating", "plugin": "wrong-kind@1"},
        "confidence_threshold": 0.8}]
    with pytest.raises(APIError) as judge:
        client.create_project(config)
    assert judge.value.status_code == 422 and b"meaning" in judge.value.body
    config = definition("bad-dataset")
    config["datasets"] = [{"source": "plugin", "name": "rows", "version": "1", "plugin": "wrong-kind@1"}]
    with pytest.raises(APIError) as dataset:
        client.create_project(config)
    assert dataset.value.status_code == 422 and b"rows" in dataset.value.body
    register(plugins, "dataset", "wrong-metric")
    with pytest.raises(APIError) as metric:
        client.generate_metric("bad-dataset", {"execution_batch_id": "unknown", "plugin": "wrong-metric@1"})
    assert metric.value.status_code == 422


def test_xvi_and_c8_deprecation_preserves_results_and_baselines(plugins):
    client, _ = plugins
    register(plugins, "validator", "retired")
    config = definition("retirement")
    config["contracts"][0]["constraints"][0].update(validator="plugin:retired@1", dimension="functional")
    client.create_project(config)
    run, [result] = trigger(client, "retirement")
    execution = run["executions"][0]["id"]
    baseline = client.approve_baseline("retirement", {"execution_id": execution, "result_id": result["id"]}).json()
    assert client.deprecate_plugin("retired@1").json()["deprecated_at"]
    assert client.list_results("retirement", execution).json() == [result]
    assert client.get_baseline("retirement", baseline["id"]).json() == baseline
    with pytest.raises(APIError) as rejected:
        client.create_project(config | {"name": "retired-binding"})
    assert rejected.value.status_code == 422
    _, [new_result] = trigger(client, "retirement")
    assert new_result["disposition"] == "oracle_unavailable"


def test_c4_plugin_registry_requires_atomic_permissions(plugins):
    admin, urls = plugins
    admin.create_role({"name": "plugin-reader", "permissions": ["read"]})
    admin.create_principal({"id": "plugin-reader", "kind": "service_account", "name": "Plugin reader",
                            "owner_person_id": "admin", "roles": ["plugin-reader"], "token": "reader-local"})
    register(plugins, "report", "restricted")
    with Client(urls["engine"], "reader-local") as reader:
        assert reader.get_plugin("restricted@1").json()["id"] == "restricted@1"
        with pytest.raises(APIError) as registration:
            reader.register_plugin({"type": "report", "name": "restricted", "version": "2",
                                    "endpoint": urls["report"], "configuration": {}})
        with pytest.raises(APIError) as deprecation:
            reader.deprecate_plugin("restricted@1")
        assert registration.value.status_code == deprecation.value.status_code == 403
