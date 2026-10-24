"""0.41.5 B introduction/B.2/B.3 and VIII/XII: complete resulting configuration."""
from copy import deepcopy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from test_execution import harness, configure, project, run, HEADERS
from test_assessment import constraint, expectation
from test_decision import gate, post
from test_scoped import control, judge
from test_review_slice_6_1 import actor
from engine.main import create_app
from engine.models.principal import PrincipalKind
from engine.validation import ConfigurationValidationError


def definition():
    p=project();p["contracts"][0]["constraints"]=[constraint(expected={"type":"string"},id="shape")]
    p["environments"].append(p["environments"][0]|{"name":"other"})
    p["suites"][0]["scenarios"].append({"name":"other","prompt":{"template":"hi"}})
    p["datasets"]=[{"name":"known","version":"1","source":"static","rows":[]}]
    p["quality_gates"]=[gate()]
    return p


def database_state(store):
    tables=("projects","suites","scenarios","environments","contracts","datasets","quality_gates",
            "custom_validators","approvals","audit_logs","executions","assessment_results","decision_records")
    with store._get_connection() as conn:
        return {table:[tuple(row) for row in conn.execute("SELECT * FROM "+table+" ORDER BY rowid")] for table in tables}


def legacy_missing_dataset(store):
    # Represent a configuration an earlier subresource route accepted, before 0.41.5.
    with store._get_connection() as conn:
        for table in ("suites","scenarios"):
            for row in conn.execute("SELECT rowid,data_json FROM "+table+" WHERE project_name='p'").fetchall():
                data=json.loads(row["data_json"])
                sc=data["scenarios"][0] if table=="suites" else data
                if sc["name"]!="a":continue
                sc.pop("variables",None);sc["dataset"]="absent@1"
                conn.execute("UPDATE "+table+" SET data_json=? WHERE rowid=?",(json.dumps(data),row["rowid"]))


ROUTES=["project_post","project_put","suite_post","scenario_post","scenario_put","scenario_delete",
        "environment_post","environment_put","environment_delete","contract_post","contract_put",
        "gate_post","gate_put","dataset_post","dataset_version","validator_post"]


def mutate(client,route,headers=HEADERS):
    root="/projects/p"
    if route.startswith("project"):
        body=client.get(root,headers=HEADERS).json()
        if route=="project_post":body["name"]="new";return client.post("/projects",json=body,headers=headers)
        return client.put(root,json=body,headers=headers)
    if route=="suite_post":return client.post(root+"/suites",json={"name":"new","scenarios":[{"name":"x","prompt":{"template":"hi"}}]},headers=headers)
    if route=="scenario_post":return client.post(root+"/suites/s/scenarios",json={"name":"new","prompt":{"template":"hi"}},headers=headers)
    if route=="scenario_put":
        body=client.get(root+"/suites/s/scenarios/a",headers=HEADERS).json();body["prompt"]={"template":"edited"}
        return client.put(root+"/suites/s/scenarios/a",json=body,headers=headers)
    if route=="scenario_delete":return client.delete(root+"/suites/s/scenarios/other",headers=headers)
    if route.startswith("environment"):
        if route=="environment_delete":return client.delete(root+"/environments/other",headers=headers)
        body=client.get(root+"/environments/test",headers=HEADERS).json();body["prompt_version"]="edited"
        if route=="environment_post":body["name"]="new";return client.post(root+"/environments",json=body,headers=headers)
        return client.put(root+"/environments/test",json=body,headers=headers)
    if route.startswith("contract"):
        body={"name":"new" if route=="contract_post" else "c","constraints":[constraint(expected={"type":"string","minLength":1},id="shape")]}
        return getattr(client,"post" if route=="contract_post" else "put")(root+"/contracts"+("" if route=="contract_post" else "/c"),json=body,headers=headers)
    if route.startswith("gate"):
        body=gate("new" if route=="gate_post" else "functional",threshold=.5)
        return getattr(client,"post" if route=="gate_post" else "put")(root+"/gates"+("" if route=="gate_post" else "/functional"),json=body,headers=headers)
    if route.startswith("dataset"):
        body={"name":"new" if route=="dataset_post" else "known","version":"2","source":"static","rows":[]}
        return client.post(root+"/datasets"+("" if route=="dataset_post" else "/known/versions"),json=body,headers=headers)
    return client.post(root+"/validators",json={"name":"new","version":"1","rule":{"operation":"equals","expected":1}},headers=headers)


@pytest.mark.parametrize("route",ROUTES)
def test_0415_b_every_configuration_route_validates_whole_result_before_any_write(harness,route):
    app,client,calls=configure(harness,definition())
    legacy_missing_dataset(app.state.storage)
    before=database_state(app.state.storage)
    reply=mutate(client,route)
    assert reply.status_code==422 and "absent@1" in reply.text,reply.text
    assert database_state(app.state.storage)==before  # Includes Approval/audit and frozen history.
    assert calls==[]


@pytest.mark.parametrize("route",["project_post","project_put","suite_post","scenario_post","scenario_put"])
@pytest.mark.parametrize("violation",["dataset","reference_oracle"])
def test_d9_b2_b3_new_invalid_scenario_rejected_on_every_containing_route(harness,route,violation):
    app,client,calls=configure(harness,definition())
    if violation=="dataset":sc={"name":"bad","prompt":{"template":"hi"},"dataset":"absent@1"}
    else:
        sc=control(name="bad")
        sc["seeded_control"].update(difficulty_prior=.8,prior_basis=1,prior_source="reference_oracles",reference_oracles=[judge()])
    before=database_state(app.state.storage)
    if route.startswith("project"):
        p=client.get("/projects/p",headers=HEADERS).json();p["suites"][0]["scenarios"].append(sc)
        if route=="project_post":p["name"]="new"
        reply=getattr(client,"post" if route=="project_post" else "put")("/projects" if route=="project_post" else "/projects/p",json=p,headers=HEADERS)
    elif route=="suite_post":reply=client.post("/projects/p/suites",json={"name":"new","scenarios":[sc]},headers=HEADERS)
    elif route=="scenario_post":reply=client.post("/projects/p/suites/s/scenarios",json=sc,headers=HEADERS)
    else:
        sc["name"]="a";reply=client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS)
    assert reply.status_code==422,reply.text
    assert ("absent@1" if violation=="dataset" else "independent") in reply.text
    assert database_state(app.state.storage)==before and calls==[]


@pytest.mark.parametrize("route",["project_post","project_put","suite_post","scenario_post","scenario_put"])
def test_0415_b3_prompt_variables_are_complete_at_load_not_after_acceptance(harness,route):
    app,client,calls=configure(harness,definition())
    sc={"name":"bad","prompt":{"template":"Hello {{missing}}"},"variables":{}}
    before=database_state(app.state.storage)
    if route.startswith("project"):
        p=client.get("/projects/p",headers=HEADERS).json();p["suites"][0]["scenarios"].append(sc)
        if route=="project_post":p["name"]="new"
        response=getattr(client,"post" if route=="project_post" else "put")("/projects" if route=="project_post" else "/projects/p",json=p,headers=HEADERS)
    elif route=="suite_post":response=client.post("/projects/p/suites",json={"name":"new","scenarios":[sc]},headers=HEADERS)
    elif route=="scenario_post":response=client.post("/projects/p/suites/s/scenarios",json=sc,headers=HEADERS)
    else:
        sc["name"]="a";response=client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS)
    assert response.status_code==422 and "missing" in response.text and "variables" in response.text
    assert database_state(app.state.storage)==before and calls==[]


@pytest.mark.parametrize("route",["dataset_post","dataset_version","project_put"])
def test_0415_b_validation_uses_resulting_registry_and_allows_repair(harness,route):
    app,client,calls=configure(harness,definition());legacy_missing_dataset(app.state.storage)
    ds={"name":"absent","version":"1","source":"static","rows":[{"id":"r","variables":{"who":"Ada"}}]}
    if route=="project_put":
        p=client.get("/projects/p",headers=HEADERS).json();p["datasets"].append(ds)
        reply=client.put("/projects/p",json=p,headers=HEADERS)
    else:reply=client.post("/projects/p/datasets"+("/absent/versions" if route=="dataset_version" else ""),json=ds,headers=HEADERS)
    assert reply.status_code==(200 if route=="project_put" else 201),reply.text
    assert run(client)["executions"][0]["opening_prompt"]=="Hello Ada"


@pytest.mark.parametrize("which",["environment","scenario","gate_dimension"])
def test_0415_b_resulting_parent_cardinality_and_coverage_are_enforced(harness,which):
    p=definition()
    if which=="environment":p["environments"]=p["environments"][:1]
    elif which=="scenario":p["suites"][0]["scenarios"]=p["suites"][0]["scenarios"][:1]
    else:
        p["contracts"]=[]
        p["suites"][0]["scenarios"][0]["contract"]={"constraints":[constraint(expected={"type":"string"})]}
        p["suites"][0]["scenarios"][1]["contract"]={"expectations":[expectation()]}
    app,client,_=configure(harness,p);before=database_state(app.state.storage)
    path="environments/test" if which=="environment" else "suites/s/scenarios/a"
    reply=client.delete("/projects/p/"+path,headers=HEADERS)
    assert reply.status_code==(422 if which=="gate_dimension" else 409),reply.text
    assert database_state(app.state.storage)==before


def test_0415_b_project_deletion_has_no_resulting_live_project_but_preserves_history(harness):
    app,client,_=configure(harness,definition());record=run(client)["executions"][0]
    assert client.delete("/projects/p?retain_history=true",headers=HEADERS).status_code==204
    assert app.state.storage.get_project("p") is None
    assert client.get("/projects/p/executions/"+record["id"],headers=HEADERS).json()==record


@pytest.mark.parametrize("kind",[PrincipalKind.PERSON,PrincipalKind.SERVICE_ACCOUNT])
def test_0415_b3_deleting_scenario_without_own_contract_keeps_ordinary_permission(harness,kind):
    app,client,_=configure(harness,definition())
    headers=actor(app,["scenario_delete"],name="deleter",kind=kind)
    approvals=app.state.storage.list_approvals("p")
    reply=client.delete("/projects/p/suites/s/scenarios/other",headers=headers)
    assert reply.status_code==204
    assert app.state.storage.list_approvals("p")==approvals


def test_0415_b_initial_load_rejects_legacy_semantically_invalid_project(harness,tmp_path):
    db=str(tmp_path/"load.db");app=create_app(db);client=TestClient(app)
    assert client.post("/projects",json=definition(),headers=HEADERS).status_code==201
    legacy_missing_dataset(app.state.storage)
    before=database_state(app.state.storage)
    with pytest.raises(ConfigurationValidationError,match="absent@1"):create_app(db)
    assert database_state(app.state.storage)==before


def test_0415_b_proposed_contract_overlays_are_used_at_load_and_change(harness):
    p=definition()
    base={"name":"base","constraints":[constraint(expected={"type":"string"})]}
    p["contracts"]=[{"name":"wrapper","extends":["base"]},base]
    app,client,_=configure(harness,p)
    assert run(client)["executions"]
    # Changing the registered ancestor must check all scopes before accepting it.
    bad={"name":"base","expectations":[expectation(judge={"model":"subject-v1","confidence_source":"self_rating"})]}
    before=database_state(app.state.storage)
    response=client.put("/projects/p/contracts/base",json=bad,headers=HEADERS)
    assert response.status_code==422 and "Independent Oracle" in response.text
    assert database_state(app.state.storage)==before


CONTRACT_ROUTES=["project_post","project_put","suite_post","scenario_post","scenario_put","scenario_delete","contract_post","contract_put","gate_post","gate_put"]


def contract_change(client,route,headers):
    p=client.get("/projects/p",headers=HEADERS).json()
    own={"constraints":[constraint(expected={"type":"string"},id="added")]}
    if route=="scenario_delete":return client.delete("/projects/p/suites/s/scenarios/a",headers=headers)
    if route.startswith("project"):
        p["suites"][0]["scenarios"][0]["contract"]=own
        if route=="project_post":p["name"]="new"
        return getattr(client,"post" if route=="project_post" else "put")("/projects" if route=="project_post" else "/projects/p",json=p,headers=headers)
    if route=="suite_post":return client.post("/projects/p/suites",json={"name":"new","contracts":[own],"scenarios":[{"name":"x","prompt":{"template":"hi"}}]},headers=headers)
    if route.startswith("scenario"):
        sc={"name":"new" if route=="scenario_post" else "a","prompt":{"template":"hi"},"contract":own}
        return getattr(client,"post" if route=="scenario_post" else "put")("/projects/p/suites/s/scenarios"+("" if route=="scenario_post" else "/a"),json=sc,headers=headers)
    return mutate(client,route,headers)


@pytest.mark.parametrize("route",CONTRACT_ROUTES)
@pytest.mark.parametrize("principal",["person","service"])
def test_0415_viii_xii_contract_changes_have_person_approval_and_service_review(harness,route,principal):
    app,client,_=configure(harness,definition())
    if route=="scenario_delete":
        sc=client.get("/projects/p/suites/s/scenarios/a",headers=HEADERS).json();sc["contract"]="c"
        assert client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS).status_code==200
    headers=actor(app,["read","project_create","project_edit","suite_create","scenario_create","scenario_edit","scenario_delete","contract_define"],name="author",kind=PrincipalKind.PERSON if principal=="person" else PrincipalKind.SERVICE_ACCOUNT)
    target="new" if route=="project_post" else "p"
    before=len(app.state.storage.list_approvals(target))
    if principal=="service":
        snapshot=database_state(app.state.storage)
        denied=contract_change(client,route,headers)
        assert denied.status_code==422 and "approved_by" in denied.text
        assert database_state(app.state.storage)==snapshot
        headers=headers|{"X-Approved-By":"admin","X-External-Review-Ref":"review-11"}
    response=contract_change(client,route,headers)
    assert response.status_code in (200,201,204),response.text
    approvals=app.state.storage.list_approvals(target)
    assert len(approvals)==before+1
    approval=approvals[0]
    assert approval.action=="contract_define" and approval.requested_by=="author"
    assert approval.approved_by==("author" if principal=="person" else "admin")
    assert approval.external_review_reference==("review-11" if principal=="service" else None)
    assert app.state.storage.list_audit_logs(target,action="contract_define")[0].details["approval_id"]==approval.id


@pytest.mark.parametrize("route",CONTRACT_ROUTES)
def test_0415_viii_every_contract_change_checks_contract_define_permission(harness,route):
    app,client,_=configure(harness,definition())
    if route=="scenario_delete":
        sc=client.get("/projects/p/suites/s/scenarios/a",headers=HEADERS).json();sc["contract"]="c"
        assert client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS).status_code==200
    headers=actor(app,["read","project_create","project_edit","suite_create","scenario_create","scenario_edit","scenario_delete"],name="author")
    before=database_state(app.state.storage)
    reply=contract_change(client,route,headers)
    assert reply.status_code==403 and "contract_define" in reply.text
    assert database_state(app.state.storage)==before


@pytest.mark.parametrize("route",CONTRACT_ROUTES)
@pytest.mark.parametrize("review",[
    {"X-External-Review-Ref":"r11"},{"X-Approved-By":"admin"},
    {"X-Approved-By":"author","X-External-Review-Ref":"r11"},
    {"X-Approved-By":"missing","X-External-Review-Ref":"r11"},
])
def test_0415_viii_service_contract_change_requires_existing_person_and_review(harness,route,review):
    app,client,_=configure(harness,definition())
    if route=="scenario_delete":
        sc=client.get("/projects/p/suites/s/scenarios/a",headers=HEADERS).json();sc["contract"]="c"
        assert client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS).status_code==200
    headers=actor(app,["read","project_create","project_edit","suite_create","scenario_create","scenario_edit","scenario_delete","contract_define"],name="author",kind=PrincipalKind.SERVICE_ACCOUNT)|review
    before=database_state(app.state.storage)
    reply=contract_change(client,route,headers)
    assert reply.status_code==422 and "Person" in reply.text
    assert database_state(app.state.storage)==before
