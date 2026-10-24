"""B.1/B.2/A MAY: omission, explicit null, typed JSON boundaries and upgrade history."""
from copy import deepcopy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from test_execution import harness, configure, project, run, HEADERS
from test_assessment import constraint, expectation
from test_decision import gate, report, post
from test_scoped import control
from engine.main import create_app


def definition():
    p=project()
    p["contracts"][0]["constraints"]=[constraint(expected={"type":"string"},id="shape")]
    p["contracts"][0]["expectations"]=[expectation()]
    p["contracts"][0]["policies"]={"validator_composition":"AND","weight":1}
    p["execution"]={"timeout":"30s"}
    p["datasets"]=[{"name":"d","version":"1","source":"static","rows":[{"id":"r","variables":{"nullable":None}}]}]
    p["defect_classes"]=[{"name":"d"}]
    return p


NULL_PATHS=[
    "execution","suites","datasets","defect_classes","contracts","quality_gates",
    "environments.0.action_boundary","execution.timeout","execution.retry","execution.scheduling",
    "execution.parallelization","execution.on_seeded_control_miss",
    "contracts.0.name","contracts.0.constraints","contracts.0.expectations","contracts.0.extends",
    "contracts.0.policies","contracts.0.policies.weight","contracts.0.policies.validator_composition",
    "contracts.0.constraints.0.id","contracts.0.constraints.0.veto","contracts.0.constraints.0.dimension",
    "contracts.0.constraints.0.defect_classes","contracts.0.expectations.0.judge",
    "contracts.0.expectations.0.multi_judge","contracts.0.expectations.0.human_reviewer",
    "contracts.0.expectations.0.confidence_threshold","contracts.0.expectations.0.review_timeout",
    "contracts.0.expectations.0.on_timeout","contracts.0.expectations.0.escalate_to",
    "contracts.0.expectations.0.id","contracts.0.expectations.0.dimension","contracts.0.expectations.0.defect_classes",
    "suites.0.contracts","suites.0.execution","suites.0.quality_gates","suites.0.scenarios.0.contract",
    "suites.0.scenarios.0.dataset","suites.0.scenarios.0.variables","suites.0.scenarios.0.seeded_control",
    "suites.0.scenarios.0.evidence","datasets.0.base_dataset","datasets.0.mechanisms","datasets.0.rows",
    "defect_classes.0.difficulty_prior","defect_classes.0.prior_basis","defect_classes.0.prior_source",
    "defect_classes.0.reference_oracles",
]


@pytest.mark.parametrize("route",["create","replace"])
@pytest.mark.parametrize("path",NULL_PATHS)
def test_b1_b2_optional_null_rejected_at_project_load_and_change_naming_field(harness,route,path):
    app,client,calls=harness
    if route=="replace":configure(harness,definition())
    payload=definition();parts=path.split(".");node=payload
    for part in parts[:-1]:node=node[int(part)] if isinstance(node,list) else node[part]
    node[parts[-1]]=None
    before=app.state.storage.list_audit_logs("p")
    response=getattr(client,"post" if route=="create" else "put")("/projects" if route=="create" else "/projects/p",json=payload,headers=HEADERS)
    assert response.status_code==422 and parts[-1] in response.text,response.text
    assert app.state.storage.list_audit_logs("p")==before and calls==[]
    assert (app.state.storage.get_project("p") is not None)==(route=="replace")


@pytest.mark.parametrize("resource,method,field",[
    ("environments/test","put","action_boundary"),("contracts/c","put","policies"),
    ("suites/s/scenarios/a","put","contract"),("gates/functional","put","min_basis"),
    ("datasets","post","base_dataset"),("datasets/d/versions","post","mechanisms"),
    ("suites","post","execution"),("suites/s/scenarios","post","dataset"),
])
def test_b2_subresource_null_is_rejected_before_writes(harness,resource,method,field):
    payload=definition();payload["quality_gates"]=[gate()]
    app,client,calls=configure(harness,payload)
    if resource.startswith("datasets"):body=deepcopy(payload["datasets"][0]);body["version"]="2"
    elif resource=="suites":body=deepcopy(payload["suites"][0]);body["name"]="other"
    elif method=="post":body=deepcopy(payload["suites"][0]["scenarios"][0]);body["name"]="other"
    else:body=client.get("/projects/p/"+resource,headers=HEADERS).json() if not resource.startswith("gates") else gate()
    body[field]=None
    before=client.get("/projects/p",headers=HEADERS).json()
    response=getattr(client,method)("/projects/p/"+resource,json=body,headers=HEADERS)
    assert response.status_code==422 and field in response.text
    assert client.get("/projects/p",headers=HEADERS).json()==before and calls==[]


@pytest.mark.parametrize("field",["artifacts","source_execution"])
def test_a4_fixed_evidence_optional_fields_are_not_nullable(harness,field):
    _,client,_=harness
    payload=project();sc=control();sc["evidence"][field]=None
    payload["contracts"]=[];payload["suites"][0]["scenarios"]=[sc]
    response=client.post("/projects",json=payload,headers=HEADERS)
    assert response.status_code==422 and field in response.text


def test_a2_a5_allowed_null_and_free_json_null_survive_get_full_put_and_history(harness):
    p=definition();p["contracts"][0]["expectations"]=[]
    p["contracts"][0]["constraints"]=[constraint("custom","response",None,dimension="functional")]
    p["contracts"][0]["policies"].pop("weight")
    p["suites"][0]["scenarios"][0]["variables"]["nullable"]=None
    p["suites"][0]["scenarios"][0]["variables"]["nested"]={"weight":None,"review_timeout":None}
    app,client,_=configure(harness,p)
    fetched=client.get("/projects/p",headers=HEADERS).json()
    assert fetched["environments"][0]["tool_configuration"] is None
    assert fetched["contracts"][0]["constraints"][0]["expected"] is None
    assert "weight" not in fetched["contracts"][0]["policies"]
    assert "contract" not in fetched["suites"][0]["scenarios"][0]
    assert fetched["suites"][0]["scenarios"][0]["variables"]["nested"]["weight"] is None
    assert client.put("/projects/p",json=fetched,headers=HEADERS).status_code==200
    assert client.get("/projects/p",headers=HEADERS).json()==fetched
    frozen=run(client)["executions"][0]
    assert frozen["configuration"]["environment"]["action_boundary"] is None
    assert frozen["configuration"]["scenario"]["contract"] is None
    assert frozen["configuration"]["contract"]["constraints"][0]["expected"] is None
    assert frozen["variables"]["nullable"] is None


@pytest.mark.parametrize("resource,body",[
    ("teams",{"id":"t","name":"T"}),("roles",{"name":"r","permissions":[]}),
    ("principals",{"id":"u","name":"U","kind":"person","token":"u"}),
])
def test_governance_requests_reject_unknown_keys(harness,resource,body):
    app,client,_=harness
    body["unknown_key"]=1
    response=client.post("/"+resource,json=body,headers=HEADERS)
    assert response.status_code==422 and "unknown_key" in response.text
    assert app.state.storage.list_audit_logs("__global__")==[]


@pytest.mark.parametrize("resource,body,field",[
    ("teams",{"id":"t","name":"T"},"description"),
    ("roles",{"name":"r"},"permissions"),
    ("principals",{"id":"u","name":"U","kind":"person"},"email"),
])
def test_governance_optional_request_field_null_is_not_omission(harness,resource,body,field):
    _,client,_=harness;body[field]=None
    response=client.post("/"+resource,json=body,headers=HEADERS)
    assert response.status_code==422 and field in response.text


def test_b2_openapi_optional_fields_have_their_type_not_nullable_default(harness):
    app,_,_=harness
    schemas=app.openapi()["components"]["schemas"]
    weight=schemas["Policies"]["properties"]["weight"]
    assert weight["type"]=="number" and "default" not in weight
    assert "weight" not in schemas["Policies"].get("required",[])
    assert any(option.get("type")=="null" for option in schemas["Environment"]["properties"]["tool_configuration"]["anyOf"])


def test_b1_b2_one_time_legacy_migration_preserves_free_json_and_frozen_bytes(harness,tmp_path):
    from engine.models.project import Project
    from engine.models.environment import Environment
    from engine.models.suite import Suite
    from engine.models.scenario import Scenario
    from engine.models.dataset import Dataset
    from engine.models.contract import Contract
    from engine.models.gate import QualityGate
    db=str(tmp_path/"legacy.db");app=create_app(db);client=TestClient(app)
    app.state.provider.call=harness[0].state.provider.call
    p=definition();p["contracts"][0]["expectations"]=[];p["quality_gates"]=[gate()]
    assert client.post("/projects",json=p,headers=HEADERS).status_code==201
    batch=run(client);r=report(client,batch["execution_batch_id"])
    post(client,"contracts",{"name":"unused","constraints":[constraint("custom","response",None,dimension="functional")]})
    models={"projects":Project,"environments":Environment,"suites":Suite,"scenarios":Scenario,"datasets":Dataset,"contracts":Contract,"quality_gates":QualityGate}
    history=("executions","assessment_results","decision_records","audit_logs","approvals")
    with sqlite3.connect(db) as conn:
        before={table:conn.execute("SELECT * FROM "+table+" ORDER BY rowid").fetchall() for table in history}
        for table,model in models.items():
            for rowid,data in conn.execute("SELECT rowid,data_json FROM "+table).fetchall():
                legacy=model.model_validate_json(data).model_dump(mode="json",context={"include_absent":True})
                conn.execute("UPDATE "+table+" SET data_json=? WHERE rowid=?",(json.dumps(legacy),rowid))
        conn.execute("DELETE FROM engine_migrations WHERE name='optional_nulls_slice_10'")
    upgraded=create_app(db);upclient=TestClient(upgraded)
    with sqlite3.connect(db) as conn:
        assert before=={table:conn.execute("SELECT * FROM "+table+" ORDER BY rowid").fetchall() for table in history}
        stored=json.loads(conn.execute("SELECT data_json FROM projects").fetchone()[0])
        assert "dataset" not in stored["suites"][0]["scenarios"][0]
        assert "base_dataset" not in stored["datasets"][0]
        assert stored["environments"][0]["tool_configuration"] is None
        assert stored["datasets"][0]["rows"][0]["variables"]["nullable"] is None
        custom=json.loads(conn.execute("SELECT data_json FROM contracts WHERE name='unused'").fetchone()[0])
        assert custom["constraints"][0]["expected"] is None
        live_after={table:conn.execute("SELECT * FROM "+table+" ORDER BY rowid").fetchall() for table in models}
    assert upclient.get("/projects/p/reports/"+r["id"],headers=HEADERS).json()==r
    from engine.decision import DecisionEngine
    assert DecisionEngine(upgraded.state.storage).current(upgraded.state.storage.decision_record("snapshot","p",r["snapshot_id"]))
    again=create_app(db)
    with sqlite3.connect(db) as conn:
        assert live_after=={table:conn.execute("SELECT * FROM "+table+" ORDER BY rowid").fetchall() for table in models}
    fetched=upclient.get("/projects/p",headers=HEADERS).json()
    assert upclient.put("/projects/p",json=fetched,headers=HEADERS).status_code==200


def test_b2_legacy_explicit_execution_null_is_rejected_not_silently_defaulted(tmp_path):
    from pydantic import ValidationError
    db=str(tmp_path/"invalid-legacy.db");app=create_app(db)
    client=TestClient(app)
    assert client.post("/projects",json=project(),headers=HEADERS).status_code==201
    with sqlite3.connect(db) as conn:
        original=json.loads(conn.execute("SELECT data_json FROM projects").fetchone()[0])
        original["execution"]={"timeout":None}
        raw=json.dumps(original)
        conn.execute("UPDATE projects SET data_json=?",(raw,))
        conn.execute("DELETE FROM engine_migrations WHERE name='optional_nulls_slice_10'")
    with pytest.raises(ValidationError,match="timeout"):
        create_app(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT data_json FROM projects").fetchone()[0]==raw
        assert conn.execute("SELECT COUNT(*) FROM engine_migrations").fetchone()[0]==0
