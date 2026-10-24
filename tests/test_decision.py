"""Slice 4 plan rules 1–10, using only project specification-derived tests."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import expectation, constraint, install_provider, results, admission
from engine.main import create_app
from engine.models.principal import Principal, PrincipalKind, Role


def gate(name="functional", **fields):
    return {"name":name, "aggregate":"functional", "threshold":1, "on_failure":"block_release"} | fields


def setup(harness, gates=None, checks=None, expectations=None):
    p = project()
    p["contracts"][0]["constraints"] = [constraint(expected={"type":"string"}, id="shape")] if checks is None else checks
    p["contracts"][0]["expectations"] = expectations or []
    p["quality_gates"] = [gate()] if gates is None else gates
    return configure(harness, p)


def post(client, path, body, expected=201, headers=HEADERS):
    reply = client.post("/projects/p/" + path, json=body, headers=headers)
    assert reply.status_code == expected, reply.text
    return reply.json()


def check(client, batch):
    return post(client, "gates/check", {"execution_batch_id":batch}, 200)


def report(client, batch):
    return post(client, "reports", {"execution_batch_id":batch})


def release_body(batch, report, decision="approved"):
    return {"execution_batch_id":batch, "report_id":report["id"], "snapshot_id":report["snapshot_id"], "decision":decision}


def test_gate_snapshot_report_release_shapes_and_trace(harness):
    app, client, _ = setup(harness)
    batch = run(client)["execution_batch_id"]
    evaluation = check(client, batch)
    g = evaluation["gates"]["functional"]
    assert g["status"] == "pass" and "reasons" not in g and "override" not in g
    assert g["value"] == 1
    assert g["basis"] == {"results":1,"not_actionable":0,"scenarios":1,"executions":1,"min_basis_met":"not_declared"}
    snapshot = client.get("/projects/p/snapshots/" + evaluation["snapshot_id"], headers=HEADERS).json()
    assert snapshot["contracts"]["c"].startswith("sha256:")
    assert snapshot["contract_contents"]["c"]["constraints"][0]["id"] == "shape"
    assert snapshot["environments"]["test"]["model_version"] == "subject-v1"
    r = report(client, batch)
    assert r["gates"] == evaluation["gates"]
    assert set(r["signals"]) == {"retries","low_confidence","multi_judge","unenforced_boundaries","boundary_attempts","unadmitted_judges"}
    assert all(isinstance(v,list) for v in r["signals"].values())
    assert all("definition" in m and "result_ids" in m for m in r["metrics"])
    decision = post(client,"releases",release_body(batch,r))
    assert decision["approved_by"] == "admin" and decision["approval_role"] == "admin"
    assert decision["gates"] == r["gates"]
    assert app.state.storage.list_audit_logs("p",action="release_decide")
    for endpoint in ("snapshots", "reports", "releases"):
        rows = client.get("/projects/p/" + endpoint + "?offset=0&limit=1",headers=HEADERS)
        assert rows.status_code == 200 and len(rows.json()) == 1


@pytest.mark.parametrize("status,confidence", [("inconclusive",.3),("actionable",.7)])
def test_confidence_before_aggregation_and_admission(harness,monkeypatch,status,confidence):
    app,client,_ = setup(harness,[gate("semantic",aggregate="semantic",min_basis={"results":2},require_admitted_judges=True)],
                         checks=[],expectations=[expectation()])
    install_provider(app,monkeypatch,reply={"verdict":"pass","confidence":confidence,"assertions":1,"explanation":"uncertain"})
    b = run(client)
    row = results(client,b["executions"][0])[0]
    assert row["disposition"] == status
    g = check(client,b["execution_batch_id"])["gates"]["semantic"]
    assert g["basis"]["results"] == 0 and g["basis"]["not_actionable"] == 1
    assert {"insufficient_basis","judge_not_admitted"} <= set(g["reasons"])
    if confidence < .7:
        assert "non_actionable_results" in g["reasons"]
    post(client,"admissions",admission(oracle=row["oracle"]))
    g = check(client,b["execution_batch_id"])["gates"]["semantic"]
    assert g["basis"]["results"] == (1 if confidence >= .7 else 0)


def test_every_numeric_failure_reason_and_safety_veto(harness):
    _,client,_ = setup(harness,[gate("safety",aggregate="safety",threshold=0,min_basis={"results":2,"scenarios":2})],
        checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="safe")])
    g = check(client,run(client)["execution_batch_id"])["gates"]["safety"]
    assert g["value"] == 0  # Meets numeric minimum zero, still vetoed.
    assert set(g["reasons"]) == {"threshold","insufficient_basis"}
    assert g["basis"]["results"] == 1 and not g["basis"]["min_basis_met"]


def test_contract_weighted_business_impact(harness):
    p=project()
    p["contracts"]=[]
    check_rule=constraint("forbidden-content","response",{"patterns":["bad"]},id="safe",dimension="functional")
    p["suites"][0]["scenarios"]=[{"name":"high","prompt":{"template":"bad"},"contract":{"constraints":[check_rule],"policies":{"weight":9}}},
        {"name":"low","prompt":{"template":"good"},"contract":{"constraints":[check_rule],"policies":{"weight":1}}}]
    p["quality_gates"]=[gate(threshold=.5)]
    app,client,_=configure(harness,p)

    async def call(model,payload,timeout):
        return {"response":payload["prompt"]}
    app.state.provider.call=call
    g=check(client,run(client)["execution_batch_id"])["gates"]["functional"]
    assert g["value"] == .1 and g["status"] == "fail"
    assert g["basis"]["scenarios"] == 2


def test_dimension_weight_map_and_resource_thresholds(harness,monkeypatch):
    gates=[gate("overall",aggregate="overall",threshold={"functional":{"min":0,"weight":9},"semantic":{"min":0,"weight":1},"overall":.9}),
           gate("resources",aggregate="functional",threshold={"latency_ms":30000,"total_tokens":12})]
    app,client,_=setup(harness,gates,expectations=[expectation()])
    install_provider(app,monkeypatch,reply={"verdict":"fail","confidence":1,"assertions":1,"explanation":"bad"})
    gs=check(client,run(client)["execution_batch_id"])["gates"]
    assert gs["overall"]["value"]["overall"] == .9 and gs["overall"]["status"] == "pass"
    assert gs["resources"]["status"] == "pass"


def test_review_linear_chain_preserves_records_and_no_subject_call(harness,monkeypatch):
    app,client,_=setup(harness,[gate("semantic",aggregate="semantic")],checks=[],expectations=[expectation()])
    calls=install_provider(app,monkeypatch,reply={"verdict":"fail","confidence":.3,"assertions":1,"explanation":"unsure"})
    b=run(client); record=b["executions"][0]; old=results(client,record)[0]
    path=f"executions/{record['id']}/results/{old['id']}/review"
    new=post(client,path,{"verdict":"pass","supporting_evidence":{"reason":"checked source"}})
    assert new["resolves"] == old["id"] and new["confidence"] == "not_applicable"
    assert results(client,record)[0] == old
    post(client,path,{"verdict":"fail","supporting_evidence":{}},409)
    post(client,f"executions/{record['id']}/results/{new['id']}/review",{"verdict":"fail","supporting_evidence":{}},409)
    assert len(calls)==2
    g=check(client,b["execution_batch_id"])["gates"]["semantic"]
    assert g["status"] == "pass" and g["basis"]["results"] == 1


def test_same_oracle_unavailable_reassessment(harness,monkeypatch):
    app,client,_=setup(harness,[gate("semantic",aggregate="semantic")],checks=[],expectations=[expectation()])
    b=run(client); record=b["executions"][0]; old=results(client,record)[0]
    assert old["disposition"]=="oracle_unavailable"
    calls=install_provider(app,monkeypatch)
    path=f"executions/{record['id']}/results/{old['id']}/reassess"
    post(client,path,{"oracle":"different"},409)
    new=post(client,path,{"oracle":old["oracle"]})
    assert new["resolves"]==old["id"] and new["verdict"]=="pass"
    assert [c[0] for c in calls]==["judge-v1"]
    post(client,path,{"oracle":old["oracle"]},409)
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["basis"]["results"]==1


@pytest.mark.parametrize("change,stale",[("environment",True),("clause",True),("add_clause",False),("unrelated_suite",False)])
def test_snapshot_staleness_and_release_scope(harness,change,stale):
    _,client,_=setup(harness)
    b=run(client); batch=b["execution_batch_id"]; r=report(client,batch)
    p=client.get("/projects/p",headers=HEADERS).json()
    if change=="environment":
        p["environments"][0]["prompt_version"]="new"
    elif change=="clause":
        p["contracts"][0]["constraints"][0]["expected"]={"type":"string","minLength":100}
    elif change=="add_clause":
        p["contracts"][0]["constraints"].append(constraint(expected={"type":"string"},id="new"))
    else:
        p["suites"].append({"name":"unrelated","scenarios":[{"name":"other","prompt":{"template":"hi"}}]})
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    post(client,"releases",release_body(batch,r),201 if change=="unrelated_suite" else 409)
    g=check(client,batch)["gates"]["functional"]
    assert ("stale_results" in g.get("reasons",[])) == stale
    if change=="add_clause":
        assert "insufficient_basis" in g["reasons"]
    assert client.get("/projects/p/reports/"+r["id"],headers=HEADERS).json()==r


def test_unnamed_clause_whole_contract_staleness(harness):
    _,client,_=setup(harness,checks=[constraint(expected={"type":"string"})])
    batch=run(client)["execution_batch_id"]
    p=client.get("/projects/p",headers=HEADERS).json()
    p["contracts"][0]["constraints"].append(constraint(expected={"type":"string"},id="added"))
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    assert "stale_results" in check(client,batch)["gates"]["functional"]["reasons"]


def test_override_bound_to_one_evaluation_and_report_freeze(harness):
    _,client,_=setup(harness,[gate(threshold=1)],checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="bad",dimension="functional")])
    batch=run(client)["execution_batch_id"]; evaluation=check(client,batch); before=report(client,batch)
    g=evaluation["gates"]["functional"]
    body={"execution_batch_id":batch,"gate_result_id":g["id"],"justification":"explicit risk acceptance"}
    post(client,"gates/functional/override",body|{"execution_batch_id":"wrong"},404)
    override=post(client,"gates/functional/override",body)
    post(client,"gates/functional/override",body,409)
    assert "override" not in before["gates"]["functional"]
    after=report(client,batch)
    assert after["gates"]["functional"]["override"]==override["approval_id"]
    post(client,"releases",release_body(batch,after,"approved"),409)
    post(client,"releases",release_body(batch,after,"overridden"))
    later=check(client,batch)
    assert later["gates"]["functional"]["id"] != g["id"]
    assert "override" not in later["gates"]["functional"]
    post(client,"releases",release_body(batch,after,"overridden"),409)
    assert client.get("/projects/p/reports/"+after["id"],headers=HEADERS).json()==after


def test_advisory_gates_in_release_no_gate_cannot_release(harness):
    _,client,_=setup(harness,[gate("warn",aggregate="semantic",on_failure="warn")],expectations=[expectation()])
    batch=run(client)["execution_batch_id"]; r=report(client,batch)
    assert r["gates"]["warn"]["status"]=="fail" and not r["gates"]["warn"]["blocking"]
    post(client,"releases",release_body(batch,r))
    post(client,"gates/warn/override",{"execution_batch_id":batch,"gate_result_id":r["gates"]["warn"]["id"],"justification":"risk"},409)
    p=client.get("/projects/p",headers=HEADERS).json();p["quality_gates"]=[]
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    r=report(client,batch)
    assert r["gates"]=={}
    post(client,"releases",release_body(batch,r),409)


def bot(app):
    app.state.storage.create_role(Role(name="automation",permissions=["release_decide","baseline_approve","gate_override","review","execute","read"]))
    app.state.storage.create_principal(Principal(id="bot",name="Bot",kind=PrincipalKind.SERVICE_ACCOUNT,owner_person_id="admin",roles=["automation"]),token="bot")
    return {"Authorization":"Bearer bot"}


def test_service_policy_scope_revocation_and_person_only_actions(harness):
    app,client,_=setup(harness); automation=bot(app)
    b=run(client); batch=b["execution_batch_id"]; record=b["executions"][0]; r=report(client,batch)
    body=release_body(batch,r)
    post(client,"releases",body,403,automation)
    policy_body={"suites":["s"],"environments":["test"],"service_accounts":["bot"]}
    post(client,"release-policies",policy_body,403,automation)
    policy=post(client,"release-policies",policy_body)
    decision=post(client,"releases",body|{"release_policy":policy["id"]},headers=automation)
    assert decision["approved_by"]=="bot"
    post(client,"baselines",{"execution_id":record["id"],"result_id":results(client,record)[0]["id"]},403,automation)
    post(client,"release-policies/"+policy["id"]+"/revoke",{},403,automation)
    post(client,"release-policies/"+policy["id"]+"/revoke",{},200)
    post(client,"releases",body|{"release_policy":policy["id"]},403,automation)
    read=client.get("/projects/p/release-policies/"+policy["id"],headers=HEADERS).json()
    assert read["revoked_by"]=="admin"
    assert client.get("/projects/p/releases/"+decision["id"],headers=HEADERS).json()==decision


def test_baseline_regression_and_snapshot_comparison(harness):
    checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="quality",dimension="functional")]
    app,client,_=setup(harness,[gate("regression",aggregate="regression",threshold=0,compare_against="latest_approved")],checks)
    response="good"

    async def call(*args):
        return {"response":response}
    app.state.provider.call=call
    first=run(client)["executions"][0]
    baseline=post(client,"baselines",{"execution_id":first["id"],"result_id":results(client,first)[0]["id"],"name":"reference"})
    assert baseline["configuration"]==first["configuration"]
    snap=post(client,"snapshots",{"suites":["s"],"environments":["test"],"baselines":[baseline["id"]]})
    response="bad"
    batch=run(client)["execution_batch_id"]
    assert check(client,batch)["gates"]["regression"]["value"]==1
    p=client.get("/projects/p",headers=HEADERS).json()
    p["quality_gates"][0]["compare_against"]=snap["id"]
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    assert check(client,batch)["gates"]["regression"]["status"]=="fail"
    r=report(client,batch)
    assert any(m["name"]=="regression_comparison" and m["value"]==1 for m in r["metrics"])


def test_seeded_evidence_excluded_and_basis_distinguishes_rows(harness):
    p=project();p["contracts"][0]["constraints"]=[constraint(expected={"type":"string"},id="shape")]
    p["quality_gates"]=[gate(min_basis={"results":3,"scenarios":2})]
    p["datasets"]=[{"name":"d","version":"1","source":"static","rows":[{"id":"1","variables":{"who":"one"}},{"id":"2","variables":{"who":"two"}}]}]
    sc=p["suites"][0]["scenarios"][0];sc.pop("variables");sc["dataset"]="d@1"
    p["suites"][0]["scenarios"].append({"name":"seed","seeded_control":{"kind":"clean","defect_class":"shape","confirmed_by":"construction"},
        "evidence":{"conversation":{"turns":[{"prompt":"fixed","response":"good"}]}}})
    _,client,_=configure(harness,p)
    g=check(client,run(client)["execution_batch_id"])["gates"]["functional"]
    assert g["basis"]=={"results":2,"not_actionable":0,"scenarios":1,"executions":2,"min_basis_met":False}


def test_empty_dataset_batch_retains_scope_and_cannot_pass(harness):
    p=project();p["quality_gates"]=[gate()]
    p["datasets"]=[{"name":"empty","version":"1","source":"static","rows":[]}]
    sc=p["suites"][0]["scenarios"][0];sc.pop("variables");sc["dataset"]="empty@1"
    _,client,calls=configure(harness,p)
    batch=run(client)
    assert batch["executions"]==[] and not calls
    g=check(client,batch["execution_batch_id"])["gates"]["functional"]
    assert g["value"]=="not_computed" and g["basis"]["results"]==0
    assert g["reasons"]==["insufficient_basis"]
    r=report(client,batch["execution_batch_id"])
    assert r["scope"]["suites"]==["s"]
    post(client,"releases",release_body(batch["execution_batch_id"],r,"rejected"))


@pytest.mark.parametrize("threshold",[{}, {"unknown":1}, {"pass_rate":"invalid"}, {"pass_rate":{"max":1,"extra":2}}])
def test_unsupported_threshold_maps_rejected(harness,threshold):
    if threshold == {"pass_rate":"invalid"}:
        _,client,_=harness
        payload=project();payload["quality_gates"]=[gate(threshold=threshold)]
        response=client.post("/projects",json=payload,headers=HEADERS)
        assert response.status_code==422 and "threshold" in response.text
        return  # B.2 numbers are now checked at load, before a batch exists.
    _,client,_=setup(harness,[gate(threshold=threshold)])
    post(client,"gates/check",{"execution_batch_id":run(client)["execution_batch_id"]},422)


def test_persistent_reports_and_history_survives_deletion(harness,monkeypatch,tmp_path):
    app=create_app(str(tmp_path/"decision.db"));client=TestClient(app)
    app.state.provider.call=harness[0].state.provider.call
    p=project();p["quality_gates"]=[gate()]
    assert client.post("/projects",json=p,headers=HEADERS).status_code==201
    batch=run(client)["execution_batch_id"]; r=report(client,batch)
    reloaded=TestClient(create_app(str(tmp_path/"decision.db")))
    assert reloaded.get("/projects/p/reports/"+r["id"],headers=HEADERS).json()==r
    assert client.delete("/projects/p",headers=HEADERS).status_code==409
    assert client.delete("/projects/p?retain_history=true",headers=HEADERS).status_code==204
    assert client.get("/projects/p/reports/"+r["id"],headers=HEADERS).json()==r


def test_suite_gates_and_gate_update_projection(harness):
    p=project();p["contracts"][0]["constraints"]=[constraint(expected={"type":"string"},id="shape")]
    p["quality_gates"]=[gate("project-gate")]
    p["suites"][0]["quality_gates"]=[gate("suite-gate",threshold=0)]
    _,client,_=configure(harness,p)
    batch=run(client)["execution_batch_id"]
    assert set(check(client,batch)["gates"])=={"project-gate","suite-gate"}
    assert {g["name"] for g in client.get("/projects/p/gates",headers=HEADERS).json()}=={"project-gate","suite-gate"}
    updated=gate("suite-gate",threshold=1.1)
    assert client.put("/projects/p/gates/suite-gate",json=updated,headers=HEADERS).status_code==200
    updated_project=gate("project-gate",threshold=.5)
    assert client.put("/projects/p/gates/project-gate",json=updated_project,headers=HEADERS).status_code==200
    current=client.get("/projects/p",headers=HEADERS).json()
    assert current["quality_gates"][0]["threshold"]==.5
    assert current["suites"][0]["quality_gates"][0]["threshold"]==1.1
    assert client.put("/projects/p",json=current,headers=HEADERS).status_code==200
    gates=check(client,batch)["gates"]
    assert gates["suite-gate"]["status"]=="fail" and gates["project-gate"]["status"]=="pass"
    post(client,"gates",gate("suite-gate"),409)


def test_report_signals_and_admission_change_invalidates_release(harness,monkeypatch):
    app,client,_=setup(harness,[gate("semantic",aggregate="semantic",require_admitted_judges=True)],checks=[],expectations=[expectation()])
    install_provider(app,monkeypatch)
    b=run(client);row=results(client,b["executions"][0])[0]
    old=report(client,b["execution_batch_id"])
    assert old["signals"]["unadmitted_judges"]==[row["oracle"]]
    post(client,"admissions",admission(oracle=row["oracle"]))
    post(client,"releases",release_body(b["execution_batch_id"],old,"rejected"),409)
    fresh=report(client,b["execution_batch_id"])
    assert fresh["signals"]["unadmitted_judges"]==[]
    post(client,"releases",release_body(b["execution_batch_id"],fresh))


def test_awaiting_review_exception_retains_recorded_at(harness):
    app,client,_=setup(harness)
    record=run(client)["executions"][0]
    old=results(client,record)[0]
    pending=old|{"id":"pending-human","oracle_type":"human_reviewer","oracle":"review-role-v1", "verdict":None,
                 "disposition":"awaiting_review","confidence":"not_applicable"}
    app.state.storage.append_result("p",pending)
    before=report(client,record["execution_batch_id"])
    assert before["gates"]["functional"]["status"]=="fail"
    path=f"executions/{record['id']}/results/pending-human/review"
    completed=post(client,path,{"verdict":"pass","supporting_evidence":{"reason":"done"}})
    assert completed["recorded_at"]==pending["recorded_at"] and completed["id"]==pending["id"]
    assert "resolves" not in completed
    after=report(client,record["execution_batch_id"])
    assert after["gates"]["functional"]["status"]=="pass"
    assert after["snapshot_id"]!=before["snapshot_id"]
    post(client,path,{"verdict":"pass","supporting_evidence":{}},409)


def test_declared_non_safety_hard_veto_cannot_be_outvoted(harness):
    _,client,_=setup(harness,[gate(threshold=0)],checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="veto",dimension="functional",veto=True)])
    g=check(client,run(client)["execution_batch_id"])["gates"]["functional"]
    assert g["value"]==0 and g["status"]=="fail"


def test_unavailable_validator_reassess_no_subject_rerun(harness,monkeypatch):
    import engine.assessment as assessment
    original=assessment.check_builtin
    app,client,calls=setup(harness)

    def crash(*args):
        raise RuntimeError("temporary checker failure")
    monkeypatch.setattr(assessment,"check_builtin",crash)
    record=run(client)["executions"][0];old=results(client,record)[0]
    monkeypatch.setattr(assessment,"check_builtin",original)
    new=post(client,f"executions/{record['id']}/results/{old['id']}/reassess",{"oracle":old["oracle"]})
    assert new["verdict"]=="pass" and new["resolves"]==old["id"]
    assert len(calls)==1


def test_failed_collection_not_green_and_uncomputed_not_threshold_failure(harness,monkeypatch):
    app,client,_=setup(harness)

    async def crash(*args):
        raise RuntimeError("offline subject")
    monkeypatch.setattr(app.state.provider,"call",crash)
    g=check(client,run(client)["execution_batch_id"])["gates"]["functional"]
    assert g["value"]=="not_computed" and g["status"]=="fail"
    assert g["reasons"]==["insufficient_basis"]


@pytest.mark.parametrize("method,path,body",[
    ("post","gates/check",{"execution_batch_id":"missing"}),
    ("post","reports",{"execution_batch_id":"missing"}),
    ("post","snapshots",{"suites":["s"],"environments":["test"]}),
    ("post","baselines",{"execution_id":"missing","result_id":"missing"}),
    ("post","release-policies",{"suites":["s"],"environments":["test"],"service_accounts":["bot"]}),
    ("get","reports",None)])
def test_decision_atomic_permissions(harness,method,path,body):
    app,client,_=setup(harness)
    app.state.storage.create_role(Role(name="no-rights",permissions=[]))
    app.state.storage.create_principal(Principal(id="none",name="None",kind=PrincipalKind.PERSON,roles=["no-rights"]),token="none")
    kwargs={"headers":{"Authorization":"Bearer none"}}
    if body is not None:kwargs["json"]=body
    reply=getattr(client,method)("/projects/p/"+path,**kwargs)
    assert reply.status_code==403


def test_gate_specific_override_permission(harness):
    app,client,_=setup(harness,[gate(override_requires="special-safety")],checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="bad",dimension="functional")])
    app.state.storage.create_role(Role(name="override-only",permissions=["gate_override"]))
    app.state.storage.create_principal(Principal(id="person",name="Person",kind=PrincipalKind.PERSON,roles=["override-only"]),token="person")
    batch=run(client)["execution_batch_id"];g=check(client,batch)["gates"]["functional"]
    post(client,"gates/functional/override",{"execution_batch_id":batch,"gate_result_id":g["id"],"justification":"risk"},403,{"Authorization":"Bearer person"})
    post(client,"gates/functional/override",{"execution_batch_id":batch,"gate_result_id":g["id"],"justification":" "},422)


def test_low_confidence_signal_retained_after_resolution(harness,monkeypatch):
    app,client,_=setup(harness,[gate("semantic",aggregate="semantic")],checks=[],expectations=[expectation()])
    install_provider(app,monkeypatch,reply={"verdict":"pass","confidence":.2,"assertions":1,"explanation":"unsure"})
    batch=run(client);record=batch["executions"][0];row=results(client,record)[0]
    r=report(client,batch["execution_batch_id"])
    assert r["signals"]["low_confidence"][0]["inconclusive"]==1
    post(client,f"executions/{record['id']}/results/{row['id']}/review",{"verdict":"pass","supporting_evidence":"inspected"})
    r=report(client,batch["execution_batch_id"])
    assert r["signals"]["low_confidence"][0]["inconclusive"]==1
    assert r["gates"]["semantic"]["basis"]["results"]==1


def test_d4_c10_low_confidence_includes_zero_inconclusive_denominators(harness,monkeypatch):
    # Appendix C C.10 Signals; I Ch.6 Aggregate Basis: every Scenario/Oracle pair,
    # including 0 of 1, is needed to distinguish 2 of 2 from 2 of 3.
    p=project();p["contracts"][0]["constraints"]=[]
    p["contracts"][0]["expectations"]=[expectation()]
    p["suites"][0]["scenarios"]=[{"name":name,"prompt":{"template":name}} for name in ("one","two","three")]
    app,client,_=configure(harness,p)
    app.state.provider.urls["judge-v1"]="http://judge.local"

    async def call(model,payload,timeout):
        if model=="subject-v1":return {"response":payload["prompt"]}
        text=payload["evidence"]["conversation"]["turns"][0]["response"]
        return {"verdict":"pass","confidence":.9 if text=="three" else .2,"assertions":1,"explanation":"checked"}
    monkeypatch.setattr(app.state.provider,"call",call)
    r=report(client,run(client)["execution_batch_id"])
    rows=r["signals"]["low_confidence"]
    assert len(rows)==3
    assert {x["scenario"]:(x["inconclusive"],x["results"]) for x in rows}=={"s/one":(1,1),"s/two":(1,1),"s/three":(0,1)}
    assert sum(x["inconclusive"] for x in rows)==2 and sum(x["results"] for x in rows)==3


def test_rejected_service_release_and_no_override_authority(harness):
    app,client,_=setup(harness,[gate()],checks=[constraint("forbidden-content","response",{"patterns":["bad"]},id="bad",dimension="functional")])
    automation=bot(app)
    batch=run(client)["execution_batch_id"];r=report(client,batch)
    policy=post(client,"release-policies",{"suites":["s"],"environments":["test"],"service_accounts":["bot"]})
    post(client,"releases",release_body(batch,r,"rejected")|{"release_policy":policy["id"]},headers=automation)
    body={"execution_batch_id":batch,"gate_result_id":r["gates"]["functional"]["id"],"justification":"risk"}
    post(client,"gates/functional/override",body,403,automation)
    post(client,"gates/functional/override",body)
    r=report(client,batch)
    post(client,"releases",release_body(batch,r,"overridden")|{"release_policy":policy["id"]},403,automation)


@pytest.mark.parametrize("outside",["suite","environment","actor"])
def test_release_policy_must_cover_exact_scope_and_actor(harness,outside):
    app,client,_=setup(harness);automation=bot(app)
    post(client,"suites",{"name":"other","scenarios":[{"name":"other","prompt":{"template":"hello"}}]})
    env=client.get("/projects/p/environments/test",headers=HEADERS).json()|{"name":"other"}
    post(client,"environments",env)
    app.state.storage.create_principal(Principal(id="other-bot",name="Other",kind=PrincipalKind.SERVICE_ACCOUNT,owner_person_id="admin",roles=["automation"]),token="other")
    body={"suites":["other" if outside=="suite" else "s"],
          "environments":["other" if outside=="environment" else "test"],
          "service_accounts":["other-bot" if outside=="actor" else "bot"]}
    policy=post(client,"release-policies",body)
    batch=run(client)["execution_batch_id"];r=report(client,batch)
    post(client,"releases",release_body(batch,r)|{"release_policy":policy["id"]},403,automation)


def test_report_retries_and_recorded_boundary_facts(harness,monkeypatch):
    p=project();p["quality_gates"]=[gate()]
    p["execution"]={"retry":{"max_attempts":1,"on":"infrastructure_failure"}}
    p["environments"][0]["action_boundary"]={"enforced":False,"entries":[{"target":"test","kind":"sandbox"}]}
    app,client,_=configure(harness,p)
    calls=0

    async def call(*args):
        nonlocal calls
        calls+=1
        if calls==1:
            raise RuntimeError("transient transport failure")
        return {"response":"hello","artifacts":{"boundary_attempt":{"target":"external","blocked":True,"tripwire":True}}}
    monkeypatch.setattr(app.state.provider,"call",call)
    b=run(client);r=report(client,b["execution_batch_id"])
    assert r["signals"]["retries"]==[{"scenario":"s/a","retries":1}]
    assert r["signals"]["unenforced_boundaries"]==["test"]
    assert r["signals"]["boundary_attempts"]==[{"target":"external","blocked":True,"tripwire":True,"execution":b["executions"][0]["id"]}]
