"""Slice 5: VI Human Review/Multi Judge, VIII Seeded Controls, A/C normative forms."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from test_execution import harness, configure, run, HEADERS, BASE, project
from test_assessment import expectation, constraint, results, admission
from test_decision import post, report, check, gate, bot
from engine.models.principal import Principal, PrincipalKind, Role
from engine.assessment import judge_identity
from engine.scoped import controls


def judge(model="judge-a"):
    return {"model":model,"confidence_source":"self_rating"}


def judged(model="judge-a",classes=None):
    e=expectation(criteria="Detect the stated defect.",judge=judge(model))
    if classes is not None:e["defect_classes"]=classes
    return e


def scenario(name="ordinary",clause=None,text="ordinary"):
    return {"name":name,"prompt":{"template":text},"contract":{"expectations":[clause or judged()]}}


def control(name="defect-1",kind="defect",model="judge-a",method="construction",text=None,defect="tox",clause=None):
    sc=scenario(name,clause or judged(model,[defect]),text or ("unsafe "+name if kind=="defect" else "safe "+name))
    seed={"kind":kind,"defect_class":defect,"confirmed_by":method}
    if kind=="defect":seed["planted_defect"]="unsafe content"
    if method=="construction":
        sc["evidence"]={"conversation":{"turns":[{"prompt":name,"response":sc.pop("prompt")["template"]}]}}
    if method=="validator":seed["confirmation"]=constraint(expected={"type":"string","pattern":"unsafe" if kind=="defect" else "safe"})
    sc["seeded_control"]=seed
    return sc


def frame(scenarios,policy="skip_class"):
    p=project();p["contracts"]=[]
    p["suites"][0]["scenarios"]=scenarios
    p["execution"]={"on_seeded_control_miss":policy}
    p["quality_gates"]=[gate("semantic",aggregate="semantic")]
    return p


def provider(app,monkeypatch,verdicts=None):
    calls=[]
    app.state.provider.urls.update({name:"http://stub.local/"+name for name in ("judge-a","judge-b","judge-c","judge-fixed")})
    verdicts=verdicts or {}

    async def call(model,payload,timeout):
        calls.append((model,deepcopy(payload)))
        if model=="subject-v1":return {"response":payload["prompt"]}
        response=payload["evidence"]["conversation"]["turns"][-1]["response"]
        value=verdicts.get(model,"pass")
        value=value(response) if callable(value) else value
        if isinstance(value,Exception):raise value
        if isinstance(value,tuple):verdict,confidence=value
        else:verdict,confidence=value,.9
        return {"verdict":verdict,"confidence":confidence,"assertions":1,"explanation":"inspected"}
    monkeypatch.setattr(app.state.provider,"call",call)
    return calls


def metadata(client,record):
    return client.get(BASE+"/"+record["id"],headers=HEADERS).json()


def panel(models=("judge-a","judge-b"),threshold="majority",quorum=None,purpose="independence",method="voting",on="human_review"):
    consensus={"method":method,"on_disagreement":on}
    if method=="voting":consensus["threshold"]=threshold
    if quorum is not None:consensus["min_qualified"]=quorum
    config={"purpose":purpose,"consensus":consensus}
    if purpose=="stability":config.update(judge=judge(models[0]),samples=len(models))
    else:config["judges"]=[judge(m) for m in models]
    e=judged();e.pop("judge");e["multi_judge"]=config
    return e


def human(role="reviewer",capture=False,timeout=None,policy="block",escalate=None):
    e={"criteria":"Human sign-off.","id":"human-clause","human_reviewer":{"role":role,"captures_confidence":capture}}
    if capture:e["confidence_threshold"]=.8
    if timeout:e["review_timeout"]=timeout
    if policy!="block":e.update(on_timeout=policy,escalate_to=escalate)
    return e


def reviewer(app,role="reviewer",actor="reviewer-person"):
    app.state.storage.create_role(Role(name=role,permissions=["review","read"]))
    app.state.storage.create_principal(Principal(id=actor,name=actor,kind=PrincipalKind.PERSON,roles=[role]),token=actor)
    return {"Authorization":"Bearer "+actor}


@pytest.mark.parametrize("capture",[False,True])
def test_direct_human_role_and_completion_preserves_id_and_time(harness,monkeypatch,capture):
    app,client,_=configure(harness,frame([scenario(clause=human(capture=capture))]))
    calls=provider(app,monkeypatch)
    role=reviewer(app)
    b=run(client);record=b["executions"][0];pending=results(client,record)[0]
    assert pending["disposition"]=="awaiting_review" and pending["verdict"] is None and pending["confidence"]=="not_applicable"
    assert pending["review_route"]["role"]=="reviewer"
    path=f"executions/{record['id']}/results/{pending['id']}/review"
    post(client,path,{"verdict":"pass","supporting_evidence":"read"},403)
    if capture:post(client,path,{"verdict":"pass","supporting_evidence":"read"},422,role)
    response=post(client,path,{"verdict":"pass","supporting_evidence":"read",**({"confidence":.9} if capture else {})},headers=role)
    assert response["id"]==pending["id"] and response["recorded_at"]==pending["recorded_at"]
    assert response["confidence"]==(.9 if capture else "not_applicable")
    assert len(calls)==1
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="pass"


@pytest.mark.parametrize("policy",["block","escalate"])
def test_human_timeout_changes_routing_not_verdict(harness,monkeypatch,policy):
    app,client,_=configure(harness,frame([scenario(clause=human(timeout="PT1S",policy=policy,escalate="senior" if policy=="escalate" else None))]))
    provider(app,monkeypatch)
    ordinary=reviewer(app);senior=reviewer(app,"senior","senior-person")
    b=run(client);record=b["executions"][0];pending=results(client,record)[0]
    monkeypatch.setattr("engine.scoped.clock_now",lambda:datetime.fromisoformat(pending["recorded_at"])+timedelta(seconds=2))
    current=results(client,record)[0]
    assert current["review_route"]["state"]==("escalated" if policy=="escalate" else "timed_out")
    assert current["verdict"] is None
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="fail"
    path=f"executions/{record['id']}/results/{pending['id']}/review"
    if policy=="escalate":post(client,path,{"verdict":"pass","supporting_evidence":"done"},403,ordinary)
    post(client,path,{"verdict":"pass","supporting_evidence":"done"},headers=senior if policy=="escalate" else ordinary)


@pytest.mark.parametrize("threshold,votes,expected",[
    ("majority",("pass","pass","fail"),"pass"),("unanimous",("pass","pass","pass"),"pass"),
    (.75,("fail","fail","fail","pass"),"fail"),("unanimous",("pass","pass","fail"),None)])
def test_panel_voting_and_honest_counts(harness,monkeypatch,threshold,votes,expected):
    models=tuple("judge-"+str(i) for i in range(len(votes)))
    app,client,_=configure(harness,frame([scenario(clause=panel(models,threshold))]))
    app.state.provider.urls.update({m:"http://stub.local/"+m for m in models})
    calls=provider(app,monkeypatch,dict(zip(models,votes)))
    b=run(client);record=b["executions"][0];rows=results(client,record);r=rows[0]
    assert r["panel"]=={"configured":len(votes),"counted":len(votes)}
    assert len(r["supporting_evidence"]["member_results"])==len(votes)
    assert [model for model,_ in calls[1:]]==list(models)
    if expected is None:
        assert r["disposition"]=="awaiting_review" and r["verdict"] is None
        assert rows[1]["oracle_type"]=="human_reviewer" and rows[1]["resolves"]==r["id"]
        completed=post(client,f"executions/{record['id']}/results/{rows[1]['id']}/review",{"verdict":"pass","supporting_evidence":"arbitrated"})
        assert completed["id"]==rows[1]["id"]
    else:assert r["verdict"]==expected and r["confidence"]==.9
    assert report(client,b["execution_batch_id"])["signals"]["multi_judge"][0]["purpose"]=="independence"


def test_stability_calls_one_configuration_repeatedly(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel(("judge-a",)*3,purpose="stability"))]))
    calls=provider(app,monkeypatch)
    r=results(client,run(client)["executions"][0])[0]
    assert r["panel"]=={"configured":3,"counted":3}
    judge_calls=[p for model,p in calls if model=="judge-a"]
    assert len(judge_calls)==3 and judge_calls[0]==judge_calls[1]==judge_calls[2]


@pytest.mark.parametrize("method",["voting","confidence_weighted_mean"])
def test_consensus_disagreement_fail_and_confidence_is_not_agreement(harness,monkeypatch,method):
    clause=panel(method=method,on="fail")
    app,client,_=configure(harness,frame([scenario(clause=clause)]))
    provider(app,monkeypatch,{"judge-a":("pass",.8),"judge-b":("fail",.8)})
    rows=results(client,run(client)["executions"][0])
    assert len(rows)==1 and rows[0]["verdict"]=="fail"
    assert rows[0]["confidence"]==.8 and rows[0]["supporting_evidence"]["agreement"]==.5


def test_unavailable_member_is_not_vote(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel())]))
    provider(app,monkeypatch,{"judge-b":RuntimeError("offline")})
    r=results(client,run(client)["executions"][0])[0]
    assert r["disposition"]=="oracle_unavailable" and r["verdict"] is None
    assert r["panel"]=={"configured":2,"counted":1}


@pytest.mark.parametrize("kind,bad_verdict,outcome",[("defect","pass","missed"),("clean","fail","false_alarm")])
def test_control_first_skip_class_and_required_metadata(harness,monkeypatch,kind,bad_verdict,outcome):
    app,client,_=configure(harness,frame([scenario(clause=judged(classes=["tox"])),control(kind=kind)]))
    calls=provider(app,monkeypatch,{"judge-a":bad_verdict})
    b=run(client);ordinary=b["executions"][0];c=b["executions"][1]
    summary=metadata(client,ordinary)["seeded_control_results"][0]
    assert summary["outcome"]==outcome and summary["invalidation_scope"]=="defect_class" and summary["reason"] is None
    assert len([m for m,_ in calls if m=="judge-a"])==1
    r=results(client,ordinary)[0]
    assert r["disposition"]=="not_assessed" and r["verdict"] is None
    assert r["invalidated_by"]==[{"scenario":c["scenario"],"defect_class":"tox"}]
    g=check(client,b["execution_batch_id"])["gates"]["semantic"]
    assert ("seeded_control_false_alarm" if kind=="clean" else "seeded_control_miss") in g["reasons"]
    assert g["basis"]["results"]==0 and g["basis"]["not_actionable"]==1


def test_unrelated_oracle_and_class_continue_after_miss(harness,monkeypatch):
    scenarios=[control(),scenario("outside",judged(classes=["other"])),scenario("different",judged("judge-b",["tox"]))]
    app,client,_=configure(harness,frame(scenarios))
    calls=provider(app,monkeypatch)
    b=run(client)
    assert all(results(client,r)[0]["disposition"]=="actionable" for r in b["executions"][1:])
    assert len([m for m,_ in calls if m=="judge-a"])==2


@pytest.mark.parametrize("method,text,confirmed",[("validator","unsafe planted",True),("validator","lost on the way",False),("human_reviewer","unsafe planted",False)])
def test_confirmation_gates_inference(harness,monkeypatch,method,text,confirmed):
    app,client,_=configure(harness,frame([scenario(clause=judged(classes=["tox"])),control(method=method,text=text)]))
    provider(app,monkeypatch)
    b=run(client);summary=metadata(client,b["executions"][0])["seeded_control_results"][0]
    assert summary["outcome"]==("missed" if confirmed else "invalid")
    r=results(client,b["executions"][0])[0]
    assert r["disposition"]==("not_assessed" if confirmed else "actionable")


def test_late_human_confirmation_derives_invalidation_and_fresh_gates(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=judged(classes=["tox"])),control(method="human_reviewer")]))
    provider(app,monkeypatch)
    b=run(client);ordinary=b["executions"][0];raw=app.state.storage.list_results("p",ordinary["id"])[0]
    before=report(client,b["execution_batch_id"])
    assert before["gates"]["semantic"]["status"]=="pass"
    path=f"executions/{ordinary['id']}/seeded-controls/defect-1/confirm"
    post(client,path,{"confirmed":True,"supporting_evidence":"verified actual unsafe Evidence"})
    assert app.state.storage.list_results("p",ordinary["id"])[0]==raw
    assert results(client,ordinary)[0]["invalidated_by"]
    assert report(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="fail"
    assert client.get("/projects/p/reports/"+before["id"],headers=HEADERS).json()==before
    automation=bot(app)
    post(client,path,{"confirmed":True,"supporting_evidence":"bot claim"},403,automation)


def test_halt_run_cancels_without_subject_or_oracle_calls(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(),control()],"halt_run"))
    calls=provider(app,monkeypatch)
    b=run(client);ordinary=b["executions"][0]
    assert ordinary["status"]=="cancelled" and ordinary["conversation"] is None
    assert [m for m,_ in calls]==["judge-a"]
    c=metadata(client,ordinary)["seeded_control_results"][0]
    assert c["invalidation_scope"]=="full_run" and c["reason"]=="halt_run"
    assert "seeded_control_miss" in check(client,b["execution_batch_id"])["gates"]["semantic"]["reasons"]


def test_explicit_full_run_invalidation_reaches_other_oracles(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario("other",judged("judge-b",["other"])),control()]))
    provider(app,monkeypatch)
    b=run(client);ordinary=b["executions"][0]
    assert "invalidated_by" not in results(client,ordinary)[0]
    path=f"executions/{ordinary['id']}/seeded-controls/defect-1/invalidate"
    post(client,path,{"reason":" "},422)
    changed=post(client,path,{"reason":"Instrument risk affects entire batch"})
    assert changed["invalidation_scope"]=="full_run"
    assert results(client,ordinary)[0]["invalidated_by"]
    assert app.state.storage.list_audit_logs("p",action="seeded_control_invalidate")


@pytest.mark.parametrize("quorum,expected",[(None,"not_assessed"),(1,"actionable")])
def test_quorum_after_member_miss(harness,monkeypatch,quorum,expected):
    app,client,_=configure(harness,frame([scenario(clause=panel(quorum=quorum)),control()]))
    calls=provider(app,monkeypatch)
    b=run(client);r=results(client,b["executions"][0])[0]
    assert r["panel"]=={"configured":2,"counted":1} and r["disposition"]==expected
    assert len([m for m,_ in calls if m=="judge-a"])==1
    assert ("invalidated_by" in r)==(quorum is None)
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]==("fail" if quorum is None else "pass")


def test_stability_excludes_every_sample_after_miss(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel(("judge-a",)*3,purpose="stability",quorum=1)),control()]))
    calls=provider(app,monkeypatch)
    r=results(client,run(client)["executions"][0])[0]
    assert r["disposition"]=="not_assessed" and r["panel"]=={"configured":3,"counted":0}
    assert len([m for m,_ in calls if m=="judge-a"])==1


def test_panel_admission_requires_all_configured_members(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel())]))
    provider(app,monkeypatch)
    b=run(client);r=results(client,b["executions"][0])[0]
    members=r["supporting_evidence"]["member_results"]
    assert not app.state.storage.is_admitted("p",r["oracle"])
    post(client,"admissions",admission(oracle=members[0]["oracle"]))
    assert not app.state.storage.is_admitted("p",r["oracle"])
    post(client,"admissions",admission(oracle=members[1]["oracle"]))
    assert app.state.storage.is_admitted("p",r["oracle"])
    assert report(client,b["execution_batch_id"])["signals"]["unadmitted_judges"]==[]


def add_fresh_controls(client,kinds=("defect",),defect="tox",prefix="fresh",model="judge-fixed"):
    p=client.get("/projects/p",headers=HEADERS).json()
    added=[]
    for kind in kinds:
        sc=control(prefix+"-"+kind,kind,model,defect=defect)
        p["suites"][0]["scenarios"].append(sc);added.append(sc["name"])
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    b=run(client)
    selected=[r for r in b["executions"] if r["scenario"] in added]
    return [results(client,r)[0] for r in selected]


@pytest.mark.parametrize("kind",["defect","clean"])
def test_requalification_requires_fresh_correct_kind_and_preserves_chain(harness,monkeypatch,kind):
    app,client,_=configure(harness,frame([scenario(clause=judged(classes=["tox"])),control(kind=kind)]))
    calls=provider(app,monkeypatch,{"judge-a":"pass" if kind=="defect" else "fail",
        "judge-fixed":lambda text:"fail" if "unsafe" in text else "pass"})
    b=run(client);ordinary=b["executions"][0];old=results(client,ordinary)[0]
    path=f"executions/{ordinary['id']}/results/{old['id']}/reassess"
    post(client,path,{"oracle":old["oracle"]},409)
    corrected=judge_identity(judged("judge-fixed",["tox"]))
    post(client,path,{"oracle":corrected},409)
    fresh=add_fresh_controls(client,(kind,))[0]
    q=post(client,"requalifications",{"oracle":fresh["oracle"],"defect_class":"tox","controls":[fresh["id"]]})
    assert q["recorded_by"]=="admin"
    subject_calls=len([m for m,_ in calls if m=="subject-v1"])
    new=post(client,path,{"oracle":fresh["oracle"]})
    assert new["resolves"]==old["id"] and new["oracle"]==corrected
    assert "invalidated_by" not in results(client,ordinary)[-1]
    assert len([m for m,_ in calls if m=="subject-v1"])==subject_calls
    assert app.state.storage.list_results("p",ordinary["id"])[0]["disposition"]=="not_assessed"
    post(client,path,{"oracle":fresh["oracle"]},409)
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="pass"
    assert client.get("/projects/p/requalifications?limit=1",headers=HEADERS).json()==[q]


def test_both_miss_kinds_need_both_qualification_kinds(harness,monkeypatch):
    # A late Human confirmation lets both initial controls be scored by the same Oracle.
    scenarios=[scenario(clause=judged(classes=["tox"])),control("miss-defect",method="human_reviewer"),control("alarm-clean",kind="clean",method="human_reviewer")]
    app,client,_=configure(harness,frame(scenarios))
    provider(app,monkeypatch,{"judge-a":lambda text:"pass" if "unsafe" in text else "fail",
        "judge-fixed":lambda text:"fail" if "unsafe" in text else "pass"})
    b=run(client);ordinary=b["executions"][0]
    for name in ("miss-defect","alarm-clean"):
        post(client,f"executions/{ordinary['id']}/seeded-controls/{name}/confirm",{"confirmed":True,"supporting_evidence":"independently inspected"})
    old=results(client,ordinary)[0]
    fresh=add_fresh_controls(client,("defect","clean"))
    post(client,"requalifications",{"oracle":fresh[0]["oracle"],"defect_class":"tox","controls":[fresh[0]["id"]]})
    path=f"executions/{ordinary['id']}/results/{old['id']}/reassess"
    post(client,path,{"oracle":fresh[0]["oracle"]},409)
    post(client,"requalifications",{"oracle":fresh[1]["oracle"],"defect_class":"tox","controls":[fresh[1]["id"]]})
    resolved=post(client,path,{"oracle":fresh[0]["oracle"]})
    assert resolved["disposition"]=="actionable"


def test_requalification_for_every_invalidating_class(harness,monkeypatch):
    scenarios=[scenario(),control("control-a",method="human_reviewer",defect="a"),control("control-b",method="human_reviewer",defect="b")]
    app,client,_=configure(harness,frame(scenarios))
    provider(app,monkeypatch,{"judge-fixed":lambda text:"fail" if "unsafe" in text else "pass"})
    b=run(client);ordinary=b["executions"][0]
    for name in ("control-a","control-b"):
        post(client,f"executions/{ordinary['id']}/seeded-controls/{name}/confirm",{"confirmed":True,"supporting_evidence":"confirmed"})
    old=results(client,ordinary)[0]
    assert len(old["invalidated_by"])==2
    fresh_a=add_fresh_controls(client,defect="a",prefix="fresh-a")[0]
    post(client,"requalifications",{"oracle":fresh_a["oracle"],"defect_class":"a","controls":[fresh_a["id"]]})
    path=f"executions/{ordinary['id']}/results/{old['id']}/reassess"
    post(client,path,{"oracle":fresh_a["oracle"]},409)
    fresh_b=add_fresh_controls(client,defect="b",prefix="fresh-b")[0]
    post(client,"requalifications",{"oracle":fresh_b["oracle"],"defect_class":"b","controls":[fresh_b["id"]]})
    post(client,path,{"oracle":fresh_b["oracle"]})


def test_requalification_rejects_wrong_class_oracle_failed_and_exposed_controls(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(),control()]))
    provider(app,monkeypatch,{"judge-fixed":lambda text:"fail" if "unsafe" in text else "pass"})
    b=run(client);miss=results(client,b["executions"][1])[0]
    post(client,"requalifications",{"oracle":miss["oracle"],"defect_class":"tox","controls":[miss["id"]]},422)
    fresh=add_fresh_controls(client)[0]
    post(client,"requalifications",{"oracle":fresh["oracle"],"defect_class":"other","controls":[fresh["id"]]},422)
    post(client,"requalifications",{"oracle":miss["oracle"],"defect_class":"tox","controls":[fresh["id"]]},422)
    post(client,"requalifications",{"id":"supplied","oracle":fresh["oracle"],"defect_class":"tox","controls":[fresh["id"]]},422)
    # Reusing the exposed Scenario with a corrected Oracle is still not fresh.
    p=client.get("/projects/p",headers=HEADERS).json()
    p["suites"][0]["scenarios"][1]["contract"]["expectations"][0]["judge"]=judge("judge-fixed")
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    exposed=run(client)["executions"][1];exposed_result=results(client,exposed)[0]
    post(client,"requalifications",{"oracle":exposed_result["oracle"],"defect_class":"tox","controls":[exposed_result["id"]]},409)


@pytest.mark.parametrize("prior",[None,"not_established",0.8])
def test_difficulty_prior_provenance_and_unknown_marker(harness,monkeypatch,prior):
    sc=control()
    if prior is not None:
        sc["seeded_control"]["difficulty_prior"]=prior
        if isinstance(prior,float):sc["seeded_control"].update(prior_basis=10,prior_source="human_reviewer")
    app,client,_=configure(harness,frame([scenario(),sc]));provider(app,monkeypatch)
    b=run(client)
    c=metadata(client,b["executions"][0])["seeded_control_results"][0]
    assert c["difficulty_prior"]==("not_established" if prior is None else prior)


def test_numeric_prior_without_basis_or_nonindependent_reference_rejected(harness):
    app,client,calls=harness
    sc=control();sc["seeded_control"]["difficulty_prior"]=.5
    assert client.post("/projects",json=frame([sc]),headers=HEADERS).status_code==422
    sc["seeded_control"].update(prior_basis=4,prior_source="reference_oracles",reference_oracles=[judge()])
    response=client.post("/projects",json=frame([sc]),headers=HEADERS)
    assert response.status_code==422 and "independent" in response.text
    assert not calls


def test_zero_reference_prior_needs_human_even_for_construction(harness,monkeypatch):
    sc=control();sc["seeded_control"].update(difficulty_prior=0,prior_basis=3,prior_source="reference_oracles",reference_oracles=[judge("reference-model")])
    app,client,_=configure(harness,frame([scenario(),sc]));provider(app,monkeypatch)
    b=run(client);ordinary=b["executions"][0]
    assert metadata(client,ordinary)["seeded_control_results"][0]["outcome"]=="invalid"
    post(client,f"executions/{ordinary['id']}/seeded-controls/defect-1/confirm",{"confirmed":True,"supporting_evidence":"Human verified despite no reference catch"})
    assert metadata(client,ordinary)["seeded_control_results"][0]["outcome"]=="missed"


def test_validator_control_and_corrected_version_requalification(harness,monkeypatch):
    rule=constraint("checker@1","response",None,id="rule",dimension="functional",defect_classes=["tox"])
    ordinary={"name":"ordinary","prompt":{"template":"normal"},"contract":{"constraints":[rule]}}
    seed=control();seed["contract"]={"constraints":[rule]}
    p=frame([ordinary,seed]);p["quality_gates"]=[gate()]
    app,client,_=configure(harness,p);calls=provider(app,monkeypatch)
    post(client,"validators",{"name":"checker","version":"1","rule":{"operation":"schema","expected":{"type":"string"}}})
    first=run(client);old=results(client,first["executions"][0])[0]
    assert old["disposition"]=="not_assessed" and old["confidence"]=="not_applicable"
    post(client,"validators",{"name":"checker","version":"2","rule":{"operation":"forbidden-content","expected":{"patterns":["unsafe"]}}})
    p=client.get("/projects/p",headers=HEADERS).json()
    fresh=control("fresh-validator");fresh["contract"]={"constraints":[rule|{"validator":"checker@2"}]}
    p["suites"][0]["scenarios"].append(fresh)
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    corrected=results(client,run(client)["executions"][-1])[0]
    post(client,"requalifications",{"oracle":corrected["oracle"],"defect_class":"tox","controls":[corrected["id"]]})
    count=len(calls)
    new=post(client,f"executions/{first['executions'][0]['id']}/results/{old['id']}/reassess",{"oracle":corrected["oracle"]})
    assert new["confidence"]=="not_applicable" and new["verdict"]=="pass" and len(calls)==count
    assert check(client,first["execution_batch_id"])["gates"]["functional"]["status"]=="pass"


def test_full_run_can_be_resolved_only_with_requalification(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(),control(method="human_reviewer")]))
    provider(app,monkeypatch,{"judge-fixed":lambda text:"fail" if "unsafe" in text else "pass"})
    b=run(client);record=b["executions"][0];old=results(client,record)[0]
    post(client,f"executions/{record['id']}/seeded-controls/defect-1/confirm",{"confirmed":True,"supporting_evidence":"verified"})
    post(client,f"executions/{record['id']}/seeded-controls/defect-1/invalidate",{"reason":"Full run instrument uncertainty"})
    fresh=add_fresh_controls(client)[0]
    post(client,"requalifications",{"oracle":fresh["oracle"],"defect_class":"tox","controls":[fresh["id"]]})
    post(client,f"executions/{record['id']}/results/{old['id']}/reassess",{"oracle":fresh["oracle"]})
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="pass"


def test_corrected_human_role_never_waives_original_policy_role(harness,monkeypatch):
    h=human();seed=control(clause=h)
    app,client,_=configure(harness,frame([scenario(clause=h),seed]))
    calls=provider(app,monkeypatch);review=reviewer(app);senior=reviewer(app,"senior","senior-person")
    b=run(client);ordinary=b["executions"][0];ctrl=b["executions"][1]
    c=results(client,ctrl)[0]
    post(client,f"executions/{ctrl['id']}/results/{c['id']}/review",{"verdict":"pass","supporting_evidence":"missed defect"},headers=review)
    old=results(client,ordinary)[0]
    post(client,f"executions/{ordinary['id']}/results/{old['id']}/review",{"verdict":"pass","supporting_evidence":"original answer"},headers=review)
    p=client.get("/projects/p",headers=HEADERS).json();fresh_control=control("fresh-human",clause=human("senior"))
    p["suites"][0]["scenarios"].append(fresh_control)
    assert client.put("/projects/p",json=p,headers=HEADERS).status_code==200
    fresh=run(client)["executions"][-1];pending=results(client,fresh)[0]
    scored=post(client,f"executions/{fresh['id']}/results/{pending['id']}/review",{"verdict":"fail","supporting_evidence":"caught"},headers=senior)
    post(client,"requalifications",{"oracle":scored["oracle"],"defect_class":"tox","controls":[scored["id"]]})
    recovered=post(client,f"executions/{ordinary['id']}/results/{old['id']}/reassess",{"oracle":scored["oracle"]})
    path=f"executions/{ordinary['id']}/results/{recovered['id']}/review"
    post(client,path,{"verdict":"pass","supporting_evidence":"checked"},403,senior)
    app.state.storage.create_principal(Principal(id="dual",name="Dual",kind=PrincipalKind.PERSON,roles=["reviewer","senior"]),token="dual")
    post(client,path,{"verdict":"pass","supporting_evidence":"checked"},headers={"Authorization":"Bearer dual"})
    assert check(client,b["execution_batch_id"])["gates"]["semantic"]["status"]=="pass"


@pytest.mark.parametrize("agreement,expected",[(None,"actionable"),(.6,"awaiting_review")])
def test_confidence_weighted_consensus_keeps_agreement_separate(harness,monkeypatch,agreement,expected):
    e=panel(("judge-a","judge-b","judge-c"),method="confidence_weighted_mean");e["confidence_threshold"]=.3
    if agreement is not None:e["multi_judge"]["consensus"]["min_agreement"]=agreement
    app,client,_=configure(harness,frame([scenario(clause=e)]))
    provider(app,monkeypatch,{"judge-a":("pass",.9),"judge-b":("fail",.1),"judge-c":("fail",.1)})
    r=results(client,run(client)["executions"][0])[0]
    assert r["disposition"]==expected
    if agreement is None:
        assert r["confidence"]==pytest.approx(1.1/3) and r["supporting_evidence"]["agreement"]==pytest.approx(1/3)
        assert r["supporting_evidence"]["weighted_pass_score"]==pytest.approx(.9/1.1)


def test_panel_http_each_model_uses_own_url_and_no_new_wire_fields(harness,monkeypatch):
    import httpx,json
    from engine.providers import HTTPProvider
    app,client,_=configure(harness,frame([scenario(clause=panel())]))
    app.state.provider.urls.update({"judge-a":"http://provider-a.local/check","judge-b":"http://provider-b.local/judge"})
    requests=[];real_client=httpx.AsyncClient

    def handle(req):
        payload=json.loads(req.content);requests.append((str(req.url),payload))
        if payload["model"]=="subject-v1":return httpx.Response(200,json={"response":"ordinary"})
        return httpx.Response(200,json={"verdict":"pass","confidence":.9,"assertions":1,"explanation":"checked"})
    monkeypatch.setattr(httpx,"AsyncClient",lambda **kwargs:real_client(**kwargs,transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(app.state.provider,"call",HTTPProvider(app.state.provider.urls).call)
    r=results(client,run(client)["executions"][0])[0]
    assert [url for url,_ in requests[1:]]==["http://provider-a.local/check","http://provider-b.local/judge"]
    assert all(set(payload)=={"model","criteria","confidence_source","evidence"} for _,payload in requests[1:])
    assert requests[1][1]["evidence"]==requests[2][1]["evidence"]
    assert r["panel"]["counted"]==2


def test_panel_member_confidence_denominators_in_report(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel())]))
    provider(app,monkeypatch,{"judge-a":("pass",.9),"judge-b":("pass",.2)})
    b=run(client);rows=report(client,b["execution_batch_id"])["signals"]["low_confidence"]
    assert len(rows)==3  # panel aggregate plus both member configurations
    assert sorted(r["inconclusive"] for r in rows)==[0,1,1]
    assert all(r["results"]==1 for r in rows)


def test_clean_control_never_uses_class_difficulty_prior(harness,monkeypatch):
    p=frame([scenario(),control(kind="clean")]);p["defect_classes"]=[{"name":"tox","difficulty_prior":0,"prior_basis":5,"prior_source":"reference_oracles","reference_oracles":[judge("reference")]}]
    app,client,_=configure(harness,p);provider(app,monkeypatch)
    b=run(client);c=metadata(client,b["executions"][0])["seeded_control_results"][0]
    assert c["outcome"]=="passed" and "difficulty_prior" not in c


def test_scoped_facts_survive_restart_and_frozen_reports(harness,monkeypatch,tmp_path):
    from engine.main import create_app
    from fastapi.testclient import TestClient
    app=create_app(str(tmp_path/"scoped.db"));client=TestClient(app)
    assert client.post("/projects",json=frame([scenario(),control(method="human_reviewer")]),headers=HEADERS).status_code==201
    provider(app,monkeypatch)
    b=run(client);r=report(client,b["execution_batch_id"])
    post(client,f"executions/{b['executions'][0]['id']}/seeded-controls/defect-1/confirm",{"confirmed":True,"supporting_evidence":"checked"})
    reloaded=TestClient(create_app(str(tmp_path/"scoped.db")))
    assert metadata(reloaded,b["executions"][0])["seeded_control_results"][0]["outcome"]=="missed"
    assert results(reloaded,b["executions"][0])[0]["invalidated_by"]
    assert reloaded.get("/projects/p/reports/"+r["id"],headers=HEADERS).json()==r


def test_panel_recovery_reuses_any_member_verdict_already_returned(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(clause=panel(on="fail"))]))
    calls=provider(app,monkeypatch,{"judge-a":"fail","judge-b":RuntimeError("offline")})
    b=run(client);record=b["executions"][0];old=results(client,record)[0]
    first=old["supporting_evidence"]["member_results"][0]
    recovered_calls=provider(app,monkeypatch,{"judge-a":"pass","judge-b":"fail"})
    new=post(client,f"executions/{record['id']}/results/{old['id']}/reassess",{"oracle":old["oracle"]})
    assert [m for m,_ in recovered_calls]==["judge-b"]
    assert new["verdict"]=="fail" and new["supporting_evidence"]["member_results"][0]==first


def test_control_unavailable_recovery_updates_only_control_reported_outcome(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario(),control()]))
    provider(app,monkeypatch,{"judge-a":RuntimeError("offline")})
    b=run(client);c=b["executions"][1];old=results(client,c)[0]
    assert metadata(client,c)["seeded_control_results"][0]["outcome"]=="invalid"
    provider(app,monkeypatch,{"judge-a":"fail"})
    post(client,f"executions/{c['id']}/results/{old['id']}/reassess",{"oracle":old["oracle"]})
    summary=metadata(client,c)["seeded_control_results"][0]
    assert summary["outcome"]=="caught"
    assert app.state.storage.list_results("p",c["id"])[0]["disposition"]=="oracle_unavailable"


def test_received_verdict_with_invalid_confidence_is_not_retryable(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario()]))
    app.state.provider.urls["judge-a"]="http://stub.local"

    async def call(model,payload,timeout):
        if model=="subject-v1":return {"response":"ordinary"}
        return {"verdict":"fail","confidence":None,"assertions":1,"explanation":"invalid metadata"}
    monkeypatch.setattr(app.state.provider,"call",call)
    r=run(client)["executions"][0];old=results(client,r)[0]
    post(client,f"executions/{r['id']}/results/{old['id']}/reassess",{"oracle":old["oracle"]},409)
