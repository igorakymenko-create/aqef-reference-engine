"""D-3: C.3 replacement/I Ch.6 staleness; O-1: V Built-in Validators, owner decision."""
from copy import deepcopy

import pytest

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import constraint, results


def inline_project():
    p = project()
    p["suites"][0]["scenarios"][0]["contract"] = {
        "constraints":[constraint(id="shape")]}
    p["contracts"] = []
    return p


def extra():
    return constraint("forbidden-content", "response", {"patterns":["bad"]}, id="added")


def test_d3_c3_project_replace_updates_executed_inline_contract_and_preserves_history(harness):
    app, client, _ = configure(harness, inline_project())
    before = run(client)["executions"][0]
    prior_results = results(client, before)
    p = client.get("/projects/p", headers=HEADERS).json()
    p["suites"][0]["scenarios"][0]["contract"]["constraints"].append(extra())
    response = client.put("/projects/p", json=p, headers=HEADERS)
    assert response.status_code == 200, response.text
    after = run(client)["executions"][0]
    assert {c["id"] for c in after["configuration"]["contract"]["constraints"]} == {"shape", "added"}
    assert {r["clause"] for r in results(client, after)} == {"shape", "added"}
    assert client.get(BASE + "/" + before["id"], headers=HEADERS).json() == before
    assert results(client, before) == prior_results
    assert len(client.get("/projects/p/suites/s/scenarios/a", headers=HEADERS).json()["contract"]["constraints"]) == 2


def test_d3_c3_subresource_changes_appear_in_project_and_later_runs(harness):
    _, client, _ = configure(harness, inline_project())
    scenario = client.get("/projects/p/suites/s/scenarios/a", headers=HEADERS).json()
    scenario["contract"]["constraints"].append(extra())
    scenario["prompt"]["template"] = "Changed {{who}}"
    updated = client.put("/projects/p/suites/s/scenarios/a", json=scenario, headers=HEADERS)
    assert updated.status_code == 200
    scenario = updated.json()
    env = client.get("/projects/p/environments/test", headers=HEADERS).json()
    env["prompt_version"] = "new-version"
    assert client.put("/projects/p/environments/test", json=env, headers=HEADERS).status_code == 200
    p = client.get("/projects/p", headers=HEADERS).json()
    assert p["suites"][0]["scenarios"][0] == scenario
    assert p["environments"][0] == env
    assert client.get("/projects", headers=HEADERS).json()[0] == p
    # A GET/PUT round trip must not restore old nested configuration.
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    record = run(client)["executions"][0]
    assert record["opening_prompt"] == "Changed world"
    assert record["configuration"]["environment"] == env | {"action_boundary":None}
    assert {r["clause"] for r in results(client, record)} == {"shape", "added"}


def test_d3_c3_suite_and_scenario_creation_deletion_and_full_replacement(harness):
    _, client, _ = configure(harness, inline_project())
    suite = {"name":"new-suite", "scenarios":[{"name":"first", "prompt":{"template":"new"},
                "contract":{"constraints":[constraint(id="new-rule")]}}]}
    assert client.post("/projects/p/suites", json=suite, headers=HEADERS).status_code == 201
    second = deepcopy(suite["scenarios"][0]) | {"name":"second"}
    assert client.post("/projects/p/suites/new-suite/scenarios", json=second, headers=HEADERS).status_code == 201
    assert client.delete("/projects/p/suites/new-suite/scenarios/first", headers=HEADERS).status_code == 204
    p = client.get("/projects/p", headers=HEADERS).json()
    assert [s["name"] for s in p["suites"]] == ["s", "new-suite"]
    assert [s["name"] for s in p["suites"][1]["scenarios"]] == ["second"]
    response = client.post(BASE, json={"suite":"new-suite", "environment":"test"}, headers=HEADERS)
    assert [r["scenario"] for r in response.json()["executions"]] == ["second"]
    # Removing a Suite in full replacement removes its live child resources, too.
    p["suites"] = p["suites"][1:]
    p["suites"][0]["execution"] = {"timeout":"1s"}
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    assert client.get("/projects/p/suites/s", headers=HEADERS).status_code == 404
    assert client.get("/projects/p/suites/s/scenarios/a", headers=HEADERS).status_code == 404
    response = client.post(BASE, json={"suite":"new-suite", "environment":"test"}, headers=HEADERS)
    assert response.json()["executions"][0]["configuration"]["execution"]["timeout"] == "1s"


@pytest.mark.parametrize("binding", ["project-inline", "project-reference", "scenario-reference", "suite-reference"])
def test_d3_c3_reusable_contract_updates_take_effect_for_all_bindings(harness, binding):
    p = project()
    definition = p["contracts"][0]
    if binding != "project-inline":
        p["contracts"] = []
        p["suites"][0]["scenarios"][0]["contract"] = {"constraints":[constraint(id="local")]}
    _, client, _ = configure(harness, p)
    if binding != "project-inline":
        assert client.post("/projects/p/contracts", json=definition, headers=HEADERS).status_code == 201
        p = client.get("/projects/p", headers=HEADERS).json()
        if binding == "project-reference":
            p["contracts"] = ["c"]
        elif binding == "scenario-reference":
            p["suites"][0]["scenarios"][0]["contract"] = "c"
        else:
            p["suites"][0]["contracts"] = ["c"]
        assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    before = run(client)["executions"][0]
    definition["constraints"].append(extra())
    assert client.put("/projects/p/contracts/c", json=definition, headers=HEADERS).status_code == 200
    after = run(client)["executions"][0]
    assert "added" in {r["clause"] for r in results(client, after)}
    assert "added" not in {r["clause"] for r in results(client, before)}
    p = client.get("/projects/p", headers=HEADERS).json()
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    assert "added" in {r["clause"] for r in results(client, run(client)["executions"][0])}


def test_d3_c3_project_put_updates_environment_and_dataset_registry_atomically(harness):
    app, client, _ = configure(harness, inline_project())
    p = client.get("/projects/p", headers=HEADERS).json()
    p["datasets"] = [{"name":"inputs", "version":"v1", "source":"static", "rows":[{"id":"row", "variables":{"who":"new"}}]}]
    sc = p["suites"][0]["scenarios"][0]
    sc.pop("variables")
    sc["dataset"] = "inputs@v1"
    p["environments"][0]["prompt_version"] = "updated"
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    record = run(client)["executions"][0]
    assert record["opening_prompt"] == "Hello new"
    assert record["configuration"]["environment"]["prompt_version"] == "updated"
    p["datasets"][0]["rows"][0]["variables"]["who"] = "illegal overwrite"
    p["environments"][0]["prompt_version"] = "must rollback"
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 409
    assert app.state.storage.get_environment("p", "test").prompt_version == "updated"
    assert run(client)["executions"][0]["opening_prompt"] == "Hello new"


def test_d3_c3_project_put_replaces_named_contract_and_new_environment(harness):
    app, client, _ = configure(harness)
    p = client.get("/projects/p", headers=HEADERS).json()
    p["contracts"][0]["constraints"].append(extra())
    p["environments"] = [p["environments"][0] | {"name":"replacement", "model_version":"subject-v2"}]
    app.state.provider.urls["subject-v2"] = "http://unused.local"
    assert client.put("/projects/p", json=p, headers=HEADERS).status_code == 200
    assert client.get("/projects/p/environments/test", headers=HEADERS).status_code == 404
    assert "added" in {c["id"] for c in client.get("/projects/p/contracts/c", headers=HEADERS).json()["constraints"]}
    response = client.post(BASE, json={"suite":"s", "environment":"replacement"}, headers=HEADERS)
    record = response.json()["executions"][0]
    assert record["configuration"]["environment"]["model_version"] == "subject-v2"
    assert "added" in {r["clause"] for r in results(client, record)}


def test_d3_nested_contract_changes_still_require_governance(harness):
    from engine.models.principal import Role, Principal, PrincipalKind
    app, client, _ = configure(harness, inline_project())
    app.state.storage.create_role(Role(name="editor", permissions=["project_create", "project_edit", "suite_create", "scenario_edit"]))
    app.state.storage.create_principal(Principal(id="editor", name="Editor", kind=PrincipalKind.PERSON, roles=["editor"]), token="editor")
    editor = {"Authorization":"Bearer editor"}
    p = inline_project()
    p["suites"][0]["scenarios"][0]["contract"]["constraints"].append(extra())
    assert client.put("/projects/p", json=p, headers=editor).status_code == 403
    p["name"] = "new-project"
    assert client.post("/projects", json=p, headers=editor).status_code == 403
    suite = p["suites"][0] | {"name":"new-suite"}
    assert client.post("/projects/p/suites", json=suite, headers=editor).status_code == 403
    sc = client.get("/projects/p/suites/s/scenarios/a", headers=HEADERS).json()
    sc.pop("contract")
    assert client.put("/projects/p/suites/s/scenarios/a", json=sc, headers=editor).status_code == 403


@pytest.mark.parametrize("text,expected,target,verdict", [
    ("Hello! How can I help?", {"type":"string","minLength":1}, "response", "pass"),
    ("", {"type":"string","minLength":1}, "response", "fail"),
    ('{"some_key":42}', {"type":"object"}, "response", "fail"),
    ('{"some_key":42}', "json", "response", "pass"),
    ("plain text", "json", "response", "fail"),
    ('{"some_key":42}', {"type":"integer","minimum":40}, "response.some_key", "pass"),
    ('{"some_key":"text"}', {"type":"integer"}, "response.some_key", "fail"),
    ("plain text", True, "response", "pass"),
    ("plain text", False, "response", "fail")])
def test_o1_volume_v_schema_applies_to_evidence_value(harness, monkeypatch, text, expected, target, verdict):
    p = inline_project()
    p["suites"][0]["scenarios"][0]["contract"]["constraints"] = [constraint(target=target, expected=expected, id="schema")]
    app, client, _ = configure(harness, p)

    async def call(*args):
        return {"response":text}
    monkeypatch.setattr(app.state.provider, "call", call)
    record = run(client)["executions"][0]
    row = results(client, record)[0]
    assert row["verdict"] == verdict
    assert row["confidence"] == "not_applicable"
