"""WD 0.41.4: C.3/C.4, XII/10, VII/A.5/B.3, IV/A.8; prose-derived regressions."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import constraint, expectation, results
from test_decision import gate, post, check, report, release_body
from test_slice_8 import dataset
from engine.auth import BOOTSTRAP_PERMISSIONS
from engine.composition import compose_contracts, compose_scenario_effective_contract, effective_contract_data, ContractCompositionConflictError
from engine.models.contract import Contract
from engine.models.principal import Principal, PrincipalKind, Role


def fragment(name, mode=None, weight=None, clause=None):
    value={"name":name,"constraints":[clause or constraint(expected={"type":"string"},id=name)]}
    if mode is not None or weight is not None:
        value["policies"]={**({"validator_composition":mode} if mode is not None else {}),
                           **({"weight":weight} if weight is not None else {})}
    return value


def test_0414_c3_sync_trigger_returns_completed_executions_and_identifier(harness):
    _,client,calls=configure(harness)
    batch=run(client)
    assert batch["execution_batch_id"] and calls
    assert all(e["status"]=="completed" and e["completed_at"] and e["conversation"] for e in batch["executions"])
    assert all(e["execution_batch_id"]==batch["execution_batch_id"] for e in batch["executions"])
    assert client.get(BASE+"/"+batch["executions"][0]["id"],headers=HEADERS).json()==batch["executions"][0]


def test_0414_xii_audit_records_mutations_with_actor_and_not_reads(harness):
    app,client,_=configure(harness)
    run(client)
    before=app.state.storage.list_audit_logs("p")
    assert {r.action for r in before}>={"project_create","contract_define","execute"}
    assert all(r.principal_id=="admin" and r.principal_kind==PrincipalKind.PERSON and r.timestamp and r.details["target"] for r in before)
    for url in ("/projects/p",BASE,"/projects/p/audit?limit=1","/projects/p/approvals"):
        assert client.get(url,headers=HEADERS).status_code==200
    assert app.state.storage.list_audit_logs("p")==before


@pytest.mark.parametrize("team_ids",[[],["unrelated"]])
def test_0414_xii_10_unbound_team_scope_is_every_project_with_atomic_permissions(harness,team_ids):
    app,client,_=configure(harness)
    app.state.storage.create_role(Role(name="reader",permissions=["read"]))
    app.state.storage.create_principal(Principal(id="outside",kind=PrincipalKind.PERSON,name="Outside",team_ids=team_ids,roles=["reader"]),token="outside")
    headers={"Authorization":"Bearer outside"}
    assert client.get("/projects/p",headers=headers).status_code==200
    assert client.get("/projects/p/suites/s",headers=headers).status_code==200
    assert client.post(BASE,json={"suite":"s","environment":"test"},headers=headers).status_code==403


@pytest.mark.parametrize("permissions",[[],["admin"],["read"]])
def test_0414_c4_admin_name_or_permission_never_grants_wildcard(harness,permissions):
    app,client,_=configure(harness)
    with app.state.storage._get_connection() as conn:
        conn.execute("UPDATE roles SET permissions_json=? WHERE name='admin'",(json.dumps(permissions),))
    assert client.get("/projects/p",headers=HEADERS).status_code==(200 if "read" in permissions else 403)
    assert client.post(BASE,json={"suite":"s","environment":"test"},headers=HEADERS).status_code==403
    assert client.post("/teams",json={"id":"x","name":"X"},headers=HEADERS).status_code==403


def test_0414_c4_explicit_bootstrap_and_arbitrary_role_governed_actor_rules(harness):
    app,client,_=configure(harness)
    assert set(app.state.storage.get_role("admin").permissions)==set(BOOTSTRAP_PERMISSIONS)
    assert "admin" not in BOOTSTRAP_PERMISSIONS
    app.state.storage.create_role(Role(name="arbitrary",permissions=["execute","read","release_decide"]))
    app.state.storage.create_principal(Principal(id="person",name="P",kind=PrincipalKind.PERSON,roles=["arbitrary"]),token="person")
    payload=client.get("/projects/p",headers=HEADERS).json();payload["contracts"][0]["constraints"]=[constraint(expected={"type":"string"})]
    payload["quality_gates"]=[gate()]
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    headers={"Authorization":"Bearer person"}
    batch=client.post(BASE,json={"suite":"s","environment":"test"},headers=headers).json()
    r=report(client,batch["execution_batch_id"])
    decision=post(client,"releases",release_body(batch["execution_batch_id"],r),headers=headers)
    assert decision["approval_role"]=="arbitrary"
    app.state.storage.create_principal(Principal(id="bot9",name="B",kind=PrincipalKind.SERVICE_ACCOUNT,owner_person_id="admin",roles=["admin"]),token="bot9")
    assert client.post("/projects/p/release-policies",json={"suites":["s"],"environments":["test"],"service_accounts":["bot9"]},headers={"Authorization":"Bearer bot9"}).status_code==403


@pytest.mark.parametrize("higher",["OR","AND","hard-veto"])
@pytest.mark.parametrize("lower",["OR","AND","hard-veto"])
@pytest.mark.parametrize("via",["suite","scenario","extends"])
def test_0414_vii_a5_b3_policy_strictness_and_lower_conflicts(higher,lower,via):
    high=Contract.model_validate(fragment("high",higher))
    low=Contract.model_validate(fragment("low",lower))
    if via=="extends":low.extends=["high"]
    args=([high],[low],None) if via=="suite" else ([high],[],low) if via=="scenario" else ([],[],low)
    rank={"OR":0,"AND":1,"hard-veto":2}
    if rank[lower]<rank[higher]:
        with pytest.raises(ContractCompositionConflictError,match="validator_composition"):
            compose_scenario_effective_contract(*args,lookup_contract=lambda name:high)
    else:
        effective=compose_scenario_effective_contract(*args,lookup_contract=lambda name:high)
        assert effective.policies.validator_composition==lower
        assert len(effective.constraints)==2


@pytest.mark.parametrize("reverse",[False,True])
def test_0414_vii_same_level_strictest_policy_is_order_independent(reverse):
    peers=[Contract.model_validate(fragment("a","OR")),Contract.model_validate(fragment("b","hard-veto"))]
    if reverse:peers.reverse()
    assert compose_scenario_effective_contract(peers,[],None).policies.validator_composition=="hard-veto"
    assert compose_contracts(peers).policies.validator_composition=="hard-veto"


@pytest.mark.parametrize("operation",["project_post","project_put","suite_post","scenario_post","scenario_put","contract_post","contract_put"])
@pytest.mark.parametrize("conflict",["mode","weight"])
def test_0414_b3_policy_conflicts_rejected_on_every_configuration_change(harness,operation,conflict):
    payload=project();high=fragment("high","AND",9)
    low=fragment("low","OR" if conflict=="mode" else "AND",1,
                 deepcopy(high["constraints"][0]) if conflict=="weight" else None)
    payload["contracts"]=[high]
    app,client,calls=configure(harness,payload)
    before=client.get("/projects/p",headers=HEADERS).json()
    if operation.startswith("contract"):
        low["extends"]=["high"]
        if operation=="contract_put":post(client,"contracts",fragment("low"))
        url="/projects/p/contracts"+("/low" if operation=="contract_put" else "")
        response=getattr(client,"put" if operation=="contract_put" else "post")(url,json=low,headers=HEADERS)
    elif operation.startswith("project"):
        payload["suites"][0]["scenarios"][0]["contract"]=low
        if operation=="project_post":payload["name"]="new"
        response=getattr(client,"post" if operation=="project_post" else "put")("/projects" if operation=="project_post" else "/projects/p",json=payload,headers=HEADERS)
    else:
        sc={"name":"other","prompt":{"template":"hi"},"contract":low}
        if operation=="suite_post":response=client.post("/projects/p/suites",json={"name":"other","scenarios":[sc]},headers=HEADERS)
        elif operation=="scenario_post":response=client.post("/projects/p/suites/s/scenarios",json=sc,headers=HEADERS)
        else:
            sc["name"]="a";response=client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS)
    assert response.status_code==422,response.text
    assert ("validator_composition" if conflict=="mode" else "weight") in response.text
    assert client.get("/projects/p",headers=HEADERS).json()==before
    assert calls==[]


@pytest.mark.parametrize("kind",["data_mutation","fuzzing","edge_cases","adversarial"])
@pytest.mark.parametrize("route",["project_post","project_put","dataset_post","dataset_version"])
def test_0414_iv_a8_unoffered_mechanisms_rejected_at_every_loader(harness,kind,route):
    app,client,calls=configure(harness)
    ds=dataset();ds["mechanisms"]=[{"type":kind}]
    payload=client.get("/projects/p",headers=HEADERS).json();before=deepcopy(payload)
    if route.startswith("project"):
        payload["datasets"]=[ds]
        if route=="project_post":payload["name"]="new"
        response=getattr(client,"post" if route=="project_post" else "put")("/projects" if route=="project_post" else "/projects/p",json=payload,headers=HEADERS)
    else:response=client.post("/projects/p/datasets"+("/derived/versions" if route=="dataset_version" else ""),json=ds,headers=HEADERS)
    assert response.status_code==422 and "mechanisms" in response.text and kind in response.text
    assert client.get("/projects/p",headers=HEADERS).json()==before
    assert app.state.storage.get_dataset("p","derived","1") is None and calls==[]


def test_0414_iv_a8_empty_mechanisms_is_no_capability(harness):
    _,client,_=configure(harness)
    ds=dataset();ds["mechanisms"]=[]
    assert client.post("/projects/p/datasets",json=ds,headers=HEADERS).status_code==201


@pytest.mark.parametrize("expectations",[False,True])
@pytest.mark.parametrize("extends",[False,True])
def test_0414_vii_a5_b3_source_clause_weights_survive_execution_snapshot_and_aggregation(harness,monkeypatch,expectations,extends):
    payload=project()
    high=fragment("high","AND",9, constraint("forbidden-content","response",{"patterns":["bad"]},id="high",dimension="functional"))
    low=fragment("low","AND",1)
    if expectations:
        high.pop("constraints");high["expectations"]=[expectation(id="high",criteria="fail",dimension="functional")]
        low.pop("constraints");low["expectations"]=[expectation(id="low",criteria="pass",dimension="functional")]
    payload["contracts"]=[high]
    payload["suites"][0]["contracts"]=[low]
    payload["suites"][0]["scenarios"][0]["contract"]=fragment("own","hard-veto",2)
    payload["quality_gates"]=[gate(threshold=.5)]
    app,client,_=configure(harness,payload)
    if extends:
        payload=client.get("/projects/p",headers=HEADERS).json()
        payload["contracts"]=[{"extends":["high"],"policies":{"validator_composition":"AND","weight":7}}]
        assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    app.state.provider.urls["judge-v1"]="http://judge.local"
    async def call(model,request,timeout):
        if model=="subject-v1":return {"response":"bad answer"}
        return {"verdict":request["criteria"],"confidence":.9,"explanation":"checked","assertions":1}
    monkeypatch.setattr(app.state.provider,"call",call)
    batch=run(client);record=batch["executions"][0]
    contract=record["configuration"]["contract"]
    assert contract["policies"]["validator_composition"]=="hard-veto"
    assert contract["clause_weights"]==({"constraints":[2],"expectations":[9,1]} if expectations else {"constraints":[9,1,2],"expectations":[]})
    evaluation=check(client,batch["execution_batch_id"])
    result=evaluation["gates"]["functional"]
    assert result["value"]==.25 and result["status"]=="fail" and result["basis"]["results"]==3
    snap=client.get("/projects/p/snapshots/"+evaluation["snapshot_id"],headers=HEADERS).json()
    assert snap["effective_contracts"]["s/a"]["clause_weights"]==contract["clause_weights"]
    # A source weight edit stales its named clause, but not unrelated named clauses.
    payload=client.get("/projects/p",headers=HEADERS).json()
    payload["suites"][0]["contracts"][0]["policies"]["weight"]=3
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    later=check(client,batch["execution_batch_id"])["gates"]["functional"]
    assert "stale_results" in later["reasons"] and later["basis"]["not_actionable"]==1
    assert client.get(BASE+"/"+record["id"],headers=HEADERS).json()==record


@pytest.mark.parametrize("weight",[9,None,2])
def test_0414_b3_repeated_clause_weight_cannot_be_changed(weight):
    high=Contract.model_validate(fragment("same","AND",9))
    low=Contract.model_validate(fragment("same","AND",weight))
    if weight==9:
        effective=compose_scenario_effective_contract([high],[],low)
        assert len(effective.constraints)==1
        assert effective_contract_data(effective)["clause_weights"]["constraints"]==[9]
    else:
        with pytest.raises(ContractCompositionConflictError,match="weight"):
            compose_scenario_effective_contract([high],[],low)


def test_0414_b3_unused_extends_parent_change_cannot_create_policy_conflict(harness):
    _,client,_=configure(harness)
    post(client,"contracts",fragment("base","OR"))
    post(client,"contracts",{"name":"unused","extends":["base"],"policies":{"validator_composition":"OR"}})
    response=client.put("/projects/p/contracts/base",json=fragment("base","AND"),headers=HEADERS)
    assert response.status_code==422 and "validator_composition" in response.text
    assert client.get("/projects/p/contracts/base",headers=HEADERS).json()["policies"]["validator_composition"]=="OR"


@pytest.mark.parametrize("value",["0.75",True,False])
@pytest.mark.parametrize("field",["confidence_threshold","weight","threshold","threshold_map","min_agreement","difficulty_prior"])
def test_b2_number_fields_reject_strings_and_booleans_at_load(harness,field,value):
    _,client,_=harness
    payload=project()
    if field=="confidence_threshold":payload["contracts"][0]["expectations"]=[expectation(confidence_threshold=value)]
    elif field=="weight":payload["contracts"][0]["policies"]={"weight":value}
    elif field.startswith("threshold"):payload["quality_gates"]=[gate(threshold=value if field=="threshold" else {"functional":{"min":value}})]
    elif field=="difficulty_prior":payload["defect_classes"]=[{"name":"d","difficulty_prior":value,"prior_basis":1,"prior_source":"human_reviewer"}]
    else:payload["contracts"][0]["expectations"]=[expectation(judge=None,multi_judge={"purpose":"stability","judge":{"model":"judge-v1","confidence_source":"self_rating"},"samples":2,"consensus":{"method":"confidence_weighted_mean","min_agreement":value}})]
    response=client.post("/projects",json=payload,headers=HEADERS)
    assert response.status_code==422 and ("threshold" if field=="threshold_map" else field) in response.text


@pytest.mark.parametrize("value",[0,1,.75])
def test_b2_json_numbers_remain_valid_and_numeric_config_changes_are_strict(harness,value):
    _,client,_=configure(harness)
    good=gate(threshold=value)
    assert client.post("/projects/p/gates",json=good,headers=HEADERS).status_code==201
    bad=deepcopy(good);bad["threshold"]=str(value)
    response=client.put("/projects/p/gates/functional",json=bad,headers=HEADERS)
    assert response.status_code==422 and "threshold" in response.text
    assert client.get("/projects/p/gates",headers=HEADERS).json()[0]["threshold"]==value


@pytest.mark.parametrize("model,body,field",[
    ("consensus",{"method":"voting","threshold":True},"threshold"),
    ("consensus",{"method":"voting","min_qualified":"2"},"min_qualified"),
    ("min_basis",{"results":True},"results"),
    ("execution",{"parallelization":"2"},"parallelization"),
    ("retry",{"max_attempts":True,"on":"infrastructure_failure"},"max_attempts"),
    ("prior",{"name":"d","difficulty_prior":.5,"prior_basis":True,"prior_source":"human_reviewer"},"prior_basis"),
    ("policies",{"weight":float("inf")},"weight"),
])
def test_b2_strict_numeric_schema_fields(model,body,field):
    from engine.models.contract import ConsensusConfig,Policies
    from engine.models.gate import MinBasis
    from engine.models.execution_config import ExecutionConfig,RetryConfig
    from engine.models.project import DefectClassConfig
    cls={"consensus":ConsensusConfig,"min_basis":MinBasis,"execution":ExecutionConfig,"retry":RetryConfig,"prior":DefectClassConfig,"policies":Policies}[model]
    with pytest.raises(ValidationError,match=field):cls.model_validate(body)


@pytest.mark.parametrize("value",["false",0,1])
@pytest.mark.parametrize("field",["veto","captures_confidence","require_admitted_judges"])
def test_b2_boolean_fields_reject_coercion_at_load(harness,field,value):
    _,client,_=harness
    payload=project()
    if field=="veto":payload["contracts"][0]["constraints"][0][field]=value
    elif field=="captures_confidence":payload["contracts"][0]["expectations"]=[{"criteria":"check","human_reviewer":{"role":"reviewer",field:value}}]
    else:payload["quality_gates"]=[gate(**{field:value})]
    response=client.post("/projects",json=payload,headers=HEADERS)
    assert response.status_code==422 and field in response.text


def test_0414_vii_anonymous_clauses_keep_separate_source_weights(harness):
    payload=project()
    payload["contracts"]=[fragment("high",weight=9,clause=constraint("forbidden-content","response",{"patterns":["bad"]},dimension="functional"))]
    payload["suites"][0]["scenarios"][0]["contract"]=fragment("low",weight=1,clause=constraint(expected={"type":"string"}))
    payload["quality_gates"]=[gate(threshold=.5)]
    _,client,_=configure(harness,payload)
    batch=run(client)
    assert batch["executions"][0]["configuration"]["contract"]["clause_weights"]["constraints"]==[9,1]
    rows=results(client,batch["executions"][0])
    assert len(rows)==2 and all(r["clause"].startswith("sha256:") for r in rows)
    assert check(client,batch["execution_batch_id"])["gates"]["functional"]["value"]==.1


def test_0414_vii_legacy_uniform_frozen_contract_keeps_weight_and_currency(harness,monkeypatch):
    from engine.assessment import clause_reference
    from engine.decision import DecisionEngine
    payload=project();payload["contracts"]=[fragment("c","AND",clause=constraint(expected={"type":"string"}))]
    app,client,_=configure(harness,payload)
    record=run(client)["executions"][0]
    rows=results(client,record)
    # Simulate an earlier frozen anonymous Contract, whose source-weight field did not exist.
    legacy=deepcopy(record);legacy["configuration"]["contract"].pop("clause_weights")
    rows[0]["clause"]=clause_reference(legacy["configuration"]["contract"],"constraints",0)
    monkeypatch.setattr(app.state.storage,"list_results",lambda project,execution:rows)
    monkeypatch.setattr(app.state.storage,"get_execution",lambda project,execution:legacy)
    engine=DecisionEngine(app.state.storage)
    entries=engine.entries([legacy],engine.scope("p",["s"],["test"]))
    assert entries[0]["weight"]==1 and not entries[0]["stale"]
