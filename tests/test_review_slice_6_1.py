"""External D-6/D-7 regression cases, derived from XII and Appendix B/C only."""
from copy import deepcopy

import pytest

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import results, constraint
from test_decision import post, gate
from test_scoped import frame, scenario, control, human, provider, reviewer
from engine.models.principal import Principal, PrincipalKind, Role


def actor(app, permissions, name="actor", kind=PrincipalKind.PERSON):
    app.state.storage.create_role(Role(name=name,permissions=permissions))
    app.state.storage.create_principal(Principal(id=name,name=name,kind=kind,roles=[name],
        owner_person_id="admin" if kind==PrincipalKind.SERVICE_ACCOUNT else None),token=name)
    return {"Authorization":"Bearer "+name}


def audit(client, action, project_name="p"):
    reply=client.get(f"/projects/{project_name}/audit",params={"action":action},headers=HEADERS)
    assert reply.status_code==200,reply.text
    return reply.json()


@pytest.mark.parametrize("kind",[PrincipalKind.PERSON,PrincipalKind.SERVICE_ACCOUNT])
def test_d6_xii_principals_execution_actor_and_successful_permission_audit(harness,kind):
    app,client,_=configure(harness)
    headers=actor(app,["execute"],kind=kind)
    response=client.post(BASE,json={"suite":"s","environment":"test"},headers=headers)
    assert response.status_code==201
    record=response.json()["executions"][0]
    assert record["principal_id"]=="actor" and record["principal_kind"]==kind.value
    assert client.get(BASE+"/"+record["id"],headers=HEADERS).json()["principal_id"]=="actor"
    entries=audit(client,"execute")
    assert len(entries)==1
    assert (entries[0]["principal_id"],entries[0]["principal_kind"])==("actor",kind.value)
    assert entries[0]["details"]["target"]==BASE
    # Rejections have no successful-action audit entry.
    assert client.post(BASE,json={"suite":"missing","environment":"test"},headers=headers).status_code==404
    assert len(audit(client,"execute"))==1


def test_d6_c8_retained_project_deletion_is_audited_and_history_readable(harness):
    app,client,_=configure(harness)
    batch=run(client)
    record=batch["executions"][0]
    headers=actor(app,["project_delete"])
    assert client.delete("/projects/p",headers=headers).status_code==409
    assert audit(client,"project_delete")==[]
    assert client.delete("/projects/p?retain_history=true",headers=headers).status_code==204
    assert client.get("/projects/p",headers=HEADERS).status_code==404
    entries=audit(client,"project_delete")
    assert len(entries)==1
    assert entries[0]["principal_id"]=="actor" and entries[0]["principal_kind"]=="person"
    assert entries[0]["details"]=={"target":"/projects/p","method":"DELETE",
        "retain_history":True,"deletion_kind":"configuration_only_history_retained"}
    assert client.get(BASE+"/"+record["id"],headers=HEADERS).status_code==200
    assert client.get(BASE+"/"+record["id"]+"/conversation",headers=HEADERS).status_code==200
    assert client.get(BASE+"/"+record["id"]+"/results",headers=HEADERS).status_code==200


def test_d8_xii_reads_are_not_audited_and_global_mutations_are_logged(harness):
    app,client,_=configure(harness)
    assert client.get("/projects/p",headers=HEADERS).status_code==200
    assert audit(client,"read")==[]  # D-8 corrects D-6's overly broad read-audit request.
    assert client.post("/teams",json={"id":"new","name":"New"},headers=HEADERS).status_code==201
    entries=audit(client,"team_admin","__global__")
    assert entries[0]["details"]["target"]=="/teams"
    assert entries[0]["principal_kind"]=="person"


def test_d6_xii_human_review_confirmation_invalidation_and_subresource_deletion_audited(harness,monkeypatch):
    app,client,_=configure(harness,frame([control(method="human_reviewer"),scenario(clause=human()),scenario("spare")]))
    provider(app,monkeypatch)
    role=reviewer(app)
    batch=run(client)
    ordinary=batch["executions"][1]
    pending=results(client,ordinary)[0]
    path=f"executions/{ordinary['id']}/results/{pending['id']}/review"
    post(client,path,{"verdict":"pass","supporting_evidence":"inspected"},headers=role)
    assert any(e["principal_id"]=="reviewer-person" and e["details"]["target"].endswith("/review") for e in audit(client,"review"))
    c=batch["executions"][0]
    prefix=f"executions/{c['id']}/seeded-controls/defect-1"
    post(client,prefix+"/confirm",{"confirmed":True,"supporting_evidence":"unsafe present"},headers=role)
    post(client,prefix+"/invalidate",{"reason":"instrument failure"})
    for action in ("seeded_control_confirm","seeded_control_invalidate"):
        assert len(audit(client,action))==1
        assert audit(client,action)[0]["details"]["target"].startswith("/projects/p/executions/")
    assert client.delete("/projects/p/suites/s/scenarios/spare",headers=HEADERS).status_code==204
    assert audit(client,"scenario_delete")[0]["details"]["deletion_kind"]=="configuration_only_history_retained"


def governed_project():
    payload=project()
    payload["quality_gates"]=[gate()]
    payload["suites"][0]["contracts"]=[{"constraints":[constraint(id="suite-shape")]}]
    payload["suites"][0]["quality_gates"]=[gate("suite-gate")]
    payload["suites"][0]["scenarios"][0]["contract"]={"constraints":[constraint(id="scenario-shape")]}
    return payload


@pytest.mark.parametrize("route",["/projects/p","/projects/p/suites/s/scenarios/a"])
@pytest.mark.parametrize("kind",[PrincipalKind.PERSON,PrincipalKind.SERVICE_ACCOUNT])
@pytest.mark.parametrize("change",["variables","normalized_defaults"])
def test_d7_b3_unchanged_normalized_governed_values_need_only_edit_permission(harness,route,kind,change):
    app,client,_=configure(harness,governed_project())
    headers=actor(app,["project_edit","scenario_edit"],kind=kind)
    before=client.get(route,headers=HEADERS).json()
    body=deepcopy(before)
    sc=body["suites"][0]["scenarios"][0] if route=="/projects/p" else body
    if change=="variables":sc["variables"]["who"]="updated"
    else:
        # Defaulted false/None/[] fields are semantically unchanged after normalization.
        clause=sc["contract"]["constraints"][0]
        clause.pop("veto",None)
        clause.pop("defect_classes",None)
        clause.pop("dimension",None)
    approvals=len(app.state.storage.list_approvals("p"))
    reply=client.put(route,json=body,headers=headers)
    assert reply.status_code==200,reply.text
    assert len(app.state.storage.list_approvals("p"))==approvals
    assert not any(e.principal_id=="actor" for e in app.state.storage.list_audit_logs("p",action="contract_define"))
    assert any(e.principal_id=="actor" for e in app.state.storage.list_audit_logs("p",action="project_edit" if route=="/projects/p" else "scenario_edit"))


@pytest.mark.parametrize("level",["project_contracts","project_gates","suite_contracts","suite_gates","scenario_contract"])
@pytest.mark.parametrize("change",["add","remove","different"])
def test_d7_b3_project_nested_governed_values_added_removed_or_changed_require_governance(harness,level,change):
    app,client,_=configure(harness,governed_project())
    headers=actor(app,["project_edit"])
    before=client.get("/projects/p",headers=HEADERS).json()
    body=deepcopy(before)
    owner=body if level.startswith("project") else body["suites"][0]
    key="contracts" if level.endswith("contracts") else "quality_gates"
    if level=="scenario_contract":
        owner=owner["scenarios"][0];key="contract"
        if change=="remove":owner.pop(key)
        else:owner[key]["constraints"].append(constraint(id="new-clause"))
    elif change=="remove":owner[key]=[]
    elif change=="add":owner[key].append(gate("new-gate") if key=="quality_gates" else {"constraints":[constraint(id="new-clause")]})
    elif key=="quality_gates":owner[key][0]["threshold"]=.5
    else:owner[key][0]["constraints"][0]["expected"]={"type":"string","minLength":1}
    reply=client.put("/projects/p",json=body,headers=headers)
    assert reply.status_code==403,reply.text
    assert "contract_define" in reply.text
    assert client.get("/projects/p",headers=HEADERS).json()==before


@pytest.mark.parametrize("change",["add","remove","different"])
def test_d7_b3_scenario_contract_add_remove_change_requires_governance(harness,change):
    payload=governed_project()
    if change=="add":payload["suites"][0]["scenarios"][0].pop("contract")
    app,client,_=configure(harness,payload)
    headers=actor(app,["scenario_edit"])
    path="/projects/p/suites/s/scenarios/a"
    before=client.get(path,headers=HEADERS).json()
    body=deepcopy(before)
    if change=="remove":body.pop("contract")
    elif change=="add":body["contract"]={"constraints":[constraint(id="new-clause")]}
    else:body["contract"]["constraints"][0]["expected"]={"type":"string","minLength":1}
    assert client.put(path,json=body,headers=headers).status_code==403
    assert client.get(path,headers=HEADERS).json()==before
