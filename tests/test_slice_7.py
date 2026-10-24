"""WD 0.41.3: I Ch.6/A.10/A.12/B.3, using only specification-derived local cases."""
from copy import deepcopy

import pytest

from test_execution import harness, configure, project, run, HEADERS
from test_assessment import constraint, expectation, results
from test_decision import gate, check, post
from test_scoped import frame, scenario, control, human, provider


def test_0413_specification_version_is_consistent_on_public_metadata(harness):
    # The metadata follows the current release; the remaining rules were added in 0.41.3.
    from engine import __version__
    app,client,_=harness
    assert __version__==app.version=="0.41.4"
    assert client.get("/healthz",headers=HEADERS).json()["specification_version"]=="0.41.4"
    assert client.get("/openapi.json",headers=HEADERS).json()["info"]["version"]=="0.41.4"


def test_0413_i6_actionable_failure_is_computable_without_minimum_basis(harness,monkeypatch):
    app,client,_=configure(harness,frame([scenario()]))
    provider(app,monkeypatch,{"judge-a":"fail"})
    batch=run(client)
    g=check(client,batch["execution_batch_id"])["gates"]["semantic"]
    assert g["value"]==0 and g["basis"]["results"]==1
    assert g["basis"]["min_basis_met"]=="not_declared"
    assert g["reasons"]==["threshold"]


@pytest.mark.parametrize("threshold",[{"pass_rate":1},{"semantic":1},{"semantic":1,"functional":1}])
def test_0413_a12_uncomputed_threshold_map_uses_top_level_not_computed(harness,monkeypatch,threshold):
    payload=frame([scenario()]);payload["quality_gates"][0]["threshold"]=threshold
    app,client,_=configure(harness,payload)
    provider(app,monkeypatch,{"judge-a":RuntimeError("offline")})
    g=check(client,run(client)["execution_batch_id"])["gates"]["semantic"]
    assert g["value"]=="not_computed"
    assert {"insufficient_basis","non_actionable_results"} <= set(g["reasons"])
    assert set(g["metric_basis"])==set(threshold)


def test_0413_a12_partially_uncomputed_map_is_not_a_numeric_complete_aggregate(harness,monkeypatch):
    payload=frame([scenario()]);payload["quality_gates"][0]["threshold"]={"semantic":1,"functional":1}
    app,client,_=configure(harness,payload)
    provider(app,monkeypatch)
    g=check(client,run(client)["execution_batch_id"])["gates"]["semantic"]
    assert g["value"]=="not_computed" and g["reasons"]==["insufficient_basis"]
    assert g["metric_basis"]["semantic"]["results"]==1 and g["metric_basis"]["functional"]["results"]==0


@pytest.mark.parametrize("state",["inconclusive","unavailable","awaiting_review","missed","false_alarm","unadmitted","stale"])
def test_0413_i6_a12_b3_no_actionable_aggregate_has_insufficient_basis_and_all_other_reasons(harness,monkeypatch,state):
    ordinary=scenario(clause=human() if state=="awaiting_review" else None)
    cases=[ordinary]
    if state in ("missed","false_alarm"):
        cases.append(control(kind="clean" if state=="false_alarm" else "defect"))
    payload=frame(cases)
    if state=="unadmitted":payload["quality_gates"][0]["require_admitted_judges"]=True
    app,client,_=configure(harness,payload)
    provider(app,monkeypatch,{"judge-a":RuntimeError("offline") if state=="unavailable" else
        ("pass",.2) if state=="inconclusive" else "fail" if state=="false_alarm" else "pass"})
    batch=run(client)
    if state=="stale":
        changed=client.get("/projects/p/environments/test",headers=HEADERS).json()
        changed["prompt_version"]="changed"
        assert client.put("/projects/p/environments/test",json=changed,headers=HEADERS).status_code==200
    g=check(client,batch["execution_batch_id"])["gates"]["semantic"]
    expected="seeded_control_miss" if state=="missed" else "seeded_control_false_alarm" if state=="false_alarm" else "judge_not_admitted" if state=="unadmitted" else "stale_results" if state=="stale" else "non_actionable_results"
    assert g["value"]=="not_computed" and g["status"]=="fail"
    assert g["basis"]["results"]==0 and g["basis"]["min_basis_met"]=="not_declared"
    assert {"insufficient_basis",expected} <= set(g["reasons"])


@pytest.mark.parametrize("addition",["clause","scenario"])
def test_0413_i6_missing_current_requirement_is_uncomputed_not_numeric_partial_subset(harness,monkeypatch,addition):
    app,client,_=configure(harness,frame([scenario()]))
    provider(app,monkeypatch)
    batch=run(client)
    previous=results(client,batch["executions"][0])
    payload=client.get("/projects/p",headers=HEADERS).json()
    if addition=="clause":
        extra=expectation(id="new-requirement")
        payload["suites"][0]["scenarios"][0]["contract"]["expectations"].append(extra)
    else:payload["suites"][0]["scenarios"].append(scenario("new-scenario"))
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    g=check(client,batch["execution_batch_id"])["gates"]["semantic"]
    assert g["value"]=="not_computed" and g["reasons"]==["insufficient_basis"]
    assert g["basis"]["results"]==1  # Existing evidence is retained, not fabricated/rewritten.
    assert results(client,batch["executions"][0])==previous


def dimension_clause(dimension):
    if dimension=="semantic":return {"expectations":[expectation()]}
    if dimension=="operational":return {"constraints":[constraint("latency","duration_ms",1000)]}
    if dimension=="safety":return {"constraints":[constraint("forbidden-content","response",{"patterns":["unsafe"]})]}
    return {"constraints":[constraint()]}


@pytest.mark.parametrize("dimension",["functional","semantic","operational","safety"])
@pytest.mark.parametrize("scope",["project","suite"])
def test_0413_a10_b3_gate_coverage_defaults_and_last_dimension_removal(harness,dimension,scope):
    _,client,calls=harness
    payload=project();payload["contracts"]=[]
    sc=payload["suites"][0]["scenarios"][0]
    sc["contract"]=dimension_clause(dimension)
    destination=payload if scope=="project" else payload["suites"][0]
    destination["quality_gates"]=[gate("covered",aggregate=dimension)]
    configure(harness,payload)
    before=client.get("/projects/p",headers=HEADERS).json()
    changed=deepcopy(before)
    changed["suites"][0]["scenarios"][0]["contract"]=dimension_clause("semantic" if dimension!="semantic" else "functional")
    rejected=client.put("/projects/p",json=changed,headers=HEADERS)
    assert rejected.status_code==422 and "covered" in rejected.text and dimension in rejected.text
    assert client.get("/projects/p",headers=HEADERS).json()==before
    assert calls==[]


@pytest.mark.parametrize("scope_kind",["no_suites","wrong_dimension","control_only"])
def test_0413_a10_b3_uncovered_dimension_gate_rejected_at_initial_load(harness,scope_kind):
    _,client,calls=harness
    payload=project();payload["quality_gates"]=[gate("uncovered",aggregate="semantic")]
    if scope_kind=="no_suites":payload["suites"]=[]
    elif scope_kind=="control_only":payload["suites"][0]["scenarios"]=[control()]
    reply=client.post("/projects",json=payload,headers=HEADERS)
    assert reply.status_code==422 and "uncovered" in reply.text and "semantic" in reply.text
    assert client.get("/projects/p",headers=HEADERS).status_code==404
    assert calls==[]


def test_0413_a10_project_gate_can_use_other_suite_but_suite_gate_cannot(harness):
    _,client,_=harness
    payload=project()
    payload["suites"].append({"name":"semantic-suite","scenarios":[scenario()]})
    payload["quality_gates"]=[gate("project-semantic",aggregate="semantic")]
    configure(harness,payload)
    candidate={"name":"uncovered-suite","quality_gates":[gate("suite-semantic",aggregate="semantic")],
        "scenarios":[{"name":"functional","prompt":{"template":"hi"}}]}
    reply=client.post("/projects/p/suites",json=candidate,headers=HEADERS)
    assert reply.status_code==422 and "suite-semantic" in reply.text
    assert client.get("/projects/p/suites/uncovered-suite",headers=HEADERS).status_code==404
    # A Project Gate is valid even though one of its Suites does not feed its dimension.
    assert client.get("/projects/p",headers=HEADERS).status_code==200


@pytest.mark.parametrize("operation",["gate_post","gate_put","scenario_put","scenario_delete","project_put","make_control"])
def test_0413_a10_b3_every_configuration_change_preserves_gate_coverage_atomically(harness,operation):
    _,client,calls=harness
    payload=project()
    payload["suites"][0]["scenarios"].append(scenario("semantic-scenario"))
    payload["quality_gates"]=[gate("functional"),gate("semantic",aggregate="semantic")]
    configure(harness,payload)
    before=client.get("/projects/p",headers=HEADERS).json()
    path="/projects/p/suites/s/scenarios/semantic-scenario"
    if operation=="gate_post":reply=client.post("/projects/p/gates",json=gate("absent",aggregate="safety"),headers=HEADERS)
    elif operation=="gate_put":reply=client.put("/projects/p/gates/semantic",json=gate("semantic",aggregate="safety"),headers=HEADERS)
    elif operation=="scenario_delete":reply=client.delete(path,headers=HEADERS)
    elif operation=="project_put":
        candidate=deepcopy(before)
        candidate["suites"][0]["scenarios"].pop()
        reply=client.put("/projects/p",json=candidate,headers=HEADERS)
    else:
        candidate=client.get(path,headers=HEADERS).json()
        if operation=="make_control":candidate=control("semantic-scenario")
        else:candidate["contract"]=dimension_clause("functional")
        reply=client.put(path,json=candidate,headers=HEADERS)
    assert reply.status_code==422,reply.text
    assert client.get("/projects/p",headers=HEADERS).json()==before
    assert calls==[]


def test_0413_a10_b3_reusable_contract_extends_update_checks_all_consumers(harness):
    _,client,_=configure(harness)
    leaf={"name":"leaf",**dimension_clause("semantic")}
    post(client,"contracts",leaf)
    post(client,"contracts",{"name":"wrapper","extends":["leaf"]})
    payload=client.get("/projects/p",headers=HEADERS).json()
    payload["contracts"]=["wrapper"]
    payload["quality_gates"]=[gate("semantic",aggregate="semantic")]
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    replacement={"name":"leaf",**dimension_clause("functional")}
    rejected=client.put("/projects/p/contracts/leaf",json=replacement,headers=HEADERS)
    assert rejected.status_code==422 and "semantic" in rejected.text
    assert client.get("/projects/p/contracts/leaf",headers=HEADERS).json()["expectations"]
    # An unused definition is not a clause in this Gate's scope.
    post(client,"contracts",{"name":"unused",**dimension_clause("functional")})


def test_0413_a10_removing_gate_and_its_last_covering_clause_together_is_valid(harness):
    _,client,_=configure(harness,frame([scenario()]))
    payload=client.get("/projects/p",headers=HEADERS).json()
    payload["quality_gates"]=[]
    payload["suites"][0]["scenarios"][0]["contract"]=dimension_clause("functional")
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200


@pytest.mark.parametrize("aggregate",["overall","regression"])
def test_0413_a10_dimension_coverage_does_not_invent_rules_for_non_dimension_gates(harness,aggregate):
    _,client,_=harness
    payload=project();payload["suites"]=[];payload["contracts"]=[]
    payload["quality_gates"]=[gate("non-dimension",aggregate=aggregate)]
    assert client.post("/projects",json=payload,headers=HEADERS).status_code==201
