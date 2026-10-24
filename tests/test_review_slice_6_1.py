"""External D-6/D-7 regression cases, derived from XII and Appendix B/C only."""
from copy import deepcopy

import pytest

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import results
from test_decision import post
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


def test_d6_xii_every_checked_action_including_reads_and_global_actions_is_logged(harness):
    app,client,_=configure(harness)
    assert client.get("/projects/p",headers=HEADERS).status_code==200
    assert any(e["details"]["target"]=="/projects/p" for e in audit(client,"read"))
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
