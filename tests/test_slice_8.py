"""Slice 8 regressions from XII, III, and Appendix B/C only."""
from copy import deepcopy

import pytest

from test_execution import harness, configure, project, run, HEADERS, BASE
from test_assessment import results, admission, constraint, expectation, install_provider, assessment_project
from test_decision import post, report, check, release_body, bot, gate
from test_scoped import frame, scenario, control, human, provider, reviewer, panel
from engine.models.principal import AuditLogEntry, PrincipalKind


def test_d8_xii_c6_reading_all_audit_pages_terminates_without_mutating_history(harness):
    app, client, _ = configure(harness)
    record = run(client)["executions"][0]
    # Old read entries are immutable history, not something this correction purges.
    app.state.storage.create_audit_entry(AuditLogEntry(id="old-read",project="p",action="audit_read",
        principal_id="admin",principal_kind=PrincipalKind.PERSON,details={"target":"/projects/p/audit"}))
    before = app.state.storage.list_audit_logs("p")
    ids = []
    for offset in range(len(before) + 1):
        response = client.get("/projects/p/audit",params={"offset":offset,"limit":1},headers=HEADERS)
        assert response.status_code == 200
        page = response.json()
        if not page:
            break
        ids.append(page[0]["id"])
    else:
        pytest.fail("Reading alone must not add another audit page")
    assert ids == [entry.id for entry in before]
    for path in ("/projects/p", "/projects/p/approvals", BASE, BASE+"/"+record["id"],
                 BASE+"/"+record["id"]+"/results", "/projects", "/teams", "/roles", "/openapi.json", "/healthz"):
        assert client.get(path,headers=HEADERS).status_code == 200
    assert app.state.storage.list_audit_logs("p") == before
    assert app.state.storage.list_audit_logs("__global__") == []


def test_d8_xii_state_changing_actions_keep_actor_target_and_audit_records(harness,monkeypatch):
    seeded = control("caught",model="judge-a")
    missed = control("missed",model="judge-b",method="human_reviewer")
    app,client,_=configure(harness,frame([scenario(),scenario("human",clause=human()),seeded,missed]))
    provider(app,monkeypatch,{"judge-a":lambda text:"fail" if "unsafe" in text else "pass"})
    role=reviewer(app);bot(app)
    batch=run(client);ordinary,human_record,caught,miss=batch["executions"]
    pending=results(client,human_record)[0]
    post(client,f"executions/{human_record['id']}/results/{pending['id']}/review",
        {"verdict":"pass","supporting_evidence":"inspected"},headers=role)
    scored=results(client,caught)[0]
    post(client,"requalifications",{"oracle":scored["oracle"],"defect_class":"tox","controls":[scored["id"]]})
    post(client,"admissions",admission(oracle=scored["oracle"]))
    ordinary_result=results(client,ordinary)[0]
    post(client,"baselines",{"execution_id":ordinary["id"],"result_id":ordinary_result["id"]})
    policy=post(client,"release-policies",{"suites":["s"],"environments":["test"],"service_accounts":["bot"]})
    frozen=report(client,batch["execution_batch_id"])
    post(client,"releases",release_body(batch["execution_batch_id"],frozen))
    post(client,"release-policies/"+policy["id"]+"/revoke",{},200)
    prefix=f"executions/{miss['id']}/seeded-controls/missed"
    post(client,prefix+"/confirm",{"confirmed":True,"supporting_evidence":"plant present"},headers=role)
    post(client,prefix+"/invalidate",{"reason":"instrument failure"})
    evaluation=check(client,batch["execution_batch_id"])
    gate_result=evaluation["gates"]["semantic"]
    post(client,"gates/semantic/override",{"execution_batch_id":batch["execution_batch_id"],
        "gate_result_id":gate_result["id"],"justification":"recorded exception"})
    assert client.delete("/projects/p/suites/s/scenarios/human",headers=HEADERS).status_code == 204
    assert client.delete("/projects/p?retain_history=true",headers=HEADERS).status_code == 204
    rows=client.get("/projects/p/audit?limit=1000",headers=HEADERS).json()
    actions={r["action"] for r in rows}
    assert {"project_create","contract_define","execute","review","baseline_approve","release_decide",
        "gate_override","seeded_control_confirm","seeded_control_invalidate","scenario_delete","project_delete"} <= actions
    assert not {"read","audit_read"} & actions
    assert all(r["principal_id"] and r["principal_kind"]=="person" and r["details"]["target"] for r in rows)
    assert any(r["action"]=="execute" and r["details"]["target"].endswith("/requalifications") for r in rows)
    assert any(r["action"]=="review" and r["details"]["target"].endswith("/admissions") for r in rows)
    assert sum(r["action"]=="release_decide" for r in rows) >= 3  # policy, release, revocation


def dataset(name="derived", version="1", base=None):
    value={"name":name,"version":version,"source":"static","rows":[{"id":"r","variables":{}}]}
    if base is not None:value["base_dataset"]=base
    return value


@pytest.mark.parametrize("route",["project_post","project_put","dataset_post","dataset_version"])
@pytest.mark.parametrize("reference",["base", "base@", "@1", "missing@1", "base@missing"])
def test_b3_base_dataset_requires_a_version_and_resolution_on_every_load(harness,route,reference):
    app,client,calls=harness
    invalid=dataset(base=reference)
    payload=project();payload["datasets"]=[dataset("base")]
    if route!="project_post":configure(harness,payload)
    before=app.state.storage.get_project("p")
    if route=="project_post":
        payload["datasets"].append(invalid)
        reply=client.post("/projects",json=payload,headers=HEADERS)
    elif route=="project_put":
        payload["datasets"].append(invalid)
        reply=client.put("/projects/p",json=payload,headers=HEADERS)
    elif route=="dataset_post":reply=client.post("/projects/p/datasets",json=invalid,headers=HEADERS)
    else:reply=client.post("/projects/p/datasets/derived/versions",json=invalid,headers=HEADERS)
    assert reply.status_code==422 and "base_dataset" in reply.text,reply.text
    assert app.state.storage.get_project("p")==before
    assert app.state.storage.get_dataset("p","derived","1") is None
    assert calls==[]


@pytest.mark.parametrize("unavailable",[False,True])
def test_g8_iii_execution_completes_before_vi_judge_uses_own_timeout(harness,monkeypatch,unavailable):
    import asyncio
    from types import SimpleNamespace
    import engine.execution as execution_module
    payload=assessment_project([constraint(expected={"type":"string"})])
    payload["execution"]={"timeout":"50ms"}
    app,client,_=configure(harness,payload)
    clock=[0.0]
    monkeypatch.setattr(execution_module,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    app.state.provider.urls["judge-v1"]="http://judge.local/invoke"
    async def call(model,request,timeout):
        if model=="subject-v1":
            clock[0]=.049
            return {"response":"hello"}
        stored=app.state.storage.list_executions("p")[0]
        assert stored["status"]=="completed" and stored["conversation"]
        assert timeout==.05
        clock[0]=.2
        if unavailable:await asyncio.sleep(.2)
        return {"verdict":"pass","confidence":.9,"explanation":"checked","assertions":1}
    monkeypatch.setattr(app.state.provider,"call",call)
    record=run(client)["executions"][0]
    assert record["status"]=="completed"
    assert record["duration_ms"]==pytest.approx(49)
    judged=results(client,record)[-1]
    assert judged["disposition"]==("oracle_unavailable" if unavailable else "actionable")
    if unavailable:assert "timeout" in judged["supporting_evidence"]["attempts"][0]["error"].lower()


def test_b3_base_dataset_forward_declared_and_registered_versions_resolve(harness):
    app,client,_=harness
    payload=project()
    payload["datasets"]=[dataset(base="base@1"),dataset("base")]
    configure(harness,payload)  # A later declaration is still in the proposed Project.
    assert app.state.storage.get_dataset("p","derived","1").base_dataset=="base@1"
    registered=dataset("registered")
    post(client,"datasets",registered)
    post(client,"datasets",dataset("api-derived",base="registered@1"))
    post(client,"datasets/api-derived/versions",dataset("api-derived","2",base="base@1"))
    payload=client.get("/projects/p",headers=HEADERS).json()
    payload["datasets"]=[dataset("replacement",base="api-derived@2")]
    # Full replacement does not remove immutable registry versions previously accepted.
    assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    assert app.state.storage.get_dataset("p","replacement","1").base_dataset=="api-derived@2"


def test_b3_base_dataset_cannot_resolve_from_another_project(harness):
    _,client,_=configure(harness)
    other=project();other["name"]="other";other["datasets"]=[dataset("other-base")]
    assert client.post("/projects",json=other,headers=HEADERS).status_code==201
    rejected=client.post("/projects/p/datasets",json=dataset(base="other-base@1"),headers=HEADERS)
    assert rejected.status_code==422 and "base_dataset" in rejected.text


@pytest.mark.parametrize("evaluate",[False,True])
def test_iii_pre_run_unfed_blocking_gates_reported_before_calls_without_blocking(harness,monkeypatch,evaluate):
    payload=project()
    payload["contracts"]=[{"name":"c","constraints":[constraint(expected={"type":"string"})]}]
    payload["suites"][0]["scenarios"].append(control())  # Its semantic clause must not count.
    payload["suites"][0]["quality_gates"]=[gate("local-functional")]
    payload["suites"].append({"name":"other", "quality_gates":[gate("other-only",aggregate="semantic")],
        "scenarios":[{"name":"cover", "prompt":{"template":"hi"},"contract":{
            "expectations":[expectation()],"constraints":[constraint("latency","duration_ms",100),
                constraint("forbidden-content","response",{"patterns":[]})]}}]})
    payload["quality_gates"]=[gate(),gate("semantic",aggregate="semantic"),
        gate("operational",aggregate="operational"),gate("advisory",aggregate="safety",on_failure="warn")]
    app,client,_=configure(harness,payload)
    seen=[]
    async def call(model,request,timeout):
        seen.append(model)
        saved=app.state.storage.get_batch("p",app.state.storage.list_executions("p")[0]["execution_batch_id"])
        assert [w["gate"] for w in saved["warnings"]]==["semantic","operational"]
        return {"response":"hello"}
    monkeypatch.setattr(app.state.provider,"call",call)
    response=client.post(BASE,json={"suite":"s","environment":"test",**({"gates":["functional"]} if evaluate else {})},headers=HEADERS)
    assert response.status_code==201,response.text
    batch=response.json()
    assert seen==["subject-v1"]  # No reachability probe, no subject call for fixed control.
    assert [w["gate"] for w in batch["warnings"]]==["semantic","operational"]
    assert all(set(w)=={"gate","reason"} and w["gate"] in w["reason"] and "non-Seeded-Control" in w["reason"] for w in batch["warnings"])
    assert app.state.storage.get_batch("p",batch["execution_batch_id"])["warnings"]==batch["warnings"]
    assert all(r["status"]=="completed" for r in batch["executions"])
    if evaluate:assert batch["gate_evaluation"]["gates"]["semantic"]["status"]=="fail"


@pytest.mark.parametrize("source",["inherited","reusable","empty_dataset"])
def test_iii_pre_run_warnings_use_resolved_default_dimensions_not_runtime_basis(harness,monkeypatch,source):
    payload=project()
    sc=payload["suites"][0]["scenarios"][0]
    payload["contracts"]=[{"name":"c","constraints":[constraint(expected={"type":"string"})]}]
    if source=="inherited":
        payload["contracts"][0]["expectations"]=[expectation()]
        payload["quality_gates"]=[gate("semantic",aggregate="semantic")]
    elif source=="empty_dataset":
        payload["datasets"]=[{"name":"empty","version":"1","source":"static","rows":[]}]
        sc.pop("variables");sc["prompt"]={"template":"hi"};sc["dataset"]="empty@1"
        payload["quality_gates"]=[gate()]
    app,client,_=configure(harness,payload)
    if source=="reusable":
        post(client,"contracts",{"name":"leaf","expectations":[expectation()]})
        post(client,"contracts",{"name":"wrapper","extends":["leaf"]})
        payload=client.get("/projects/p",headers=HEADERS).json()
        payload["contracts"]=["wrapper"];payload["quality_gates"]=[gate("semantic",aggregate="semantic")]
        assert client.put("/projects/p",json=payload,headers=HEADERS).status_code==200
    calls=install_provider(app,monkeypatch)
    batch=run(client)
    assert batch["warnings"]==[]
    assert bool(calls)==(source!="empty_dataset")


@pytest.mark.parametrize("architecture",["single","independence","stability"])
def test_g4_b3_identity_rejects_subject_model_and_accepts_distinct_identifiers(harness,architecture):
    _,client,calls=harness
    exp=expectation(judge={"model":"subject-v1","confidence_source":"self_rating"}) if architecture=="single" else panel(
        ("subject-v1","judge-other"),purpose=architecture)
    payload=assessment_project(expectations=[exp])
    denied=client.post("/projects",json=payload,headers=HEADERS)
    assert denied.status_code==422 and "Independent Oracle" in denied.text
    if architecture=="single":exp["judge"]["model"]="subject-v2"
    elif architecture=="stability":exp["multi_judge"]["judge"]["model"]="subject-v2"
    else:exp["multi_judge"]["judges"][0]["model"]="subject-v2"
    # Prefix/family-looking names are not a weights attestation or an extra MUST.
    assert client.post("/projects",json=payload,headers=HEADERS).status_code==201
    assert calls==[]


@pytest.mark.parametrize("operation",["environment_post","environment_put","scenario_post","scenario_put","suite_post","contract_put"])
def test_g4_b3_identity_is_checked_before_subresource_configuration_changes(harness,operation):
    payload=project()
    if operation=="contract_put":payload=assessment_project()
    else:payload["suites"][0]["scenarios"][0]["contract"]={"expectations":[expectation()]}
    app,client,calls=configure(harness,payload)
    before=client.get("/projects/p",headers=HEADERS).json()
    identical=expectation(judge={"model":"subject-v1","confidence_source":"self_rating"})
    if operation.startswith("environment"):
        env=deepcopy(before["environments"][0]);env["model_version"]="judge-v1"
        if operation=="environment_post":
            env["name"]="other";reply=client.post("/projects/p/environments",json=env,headers=HEADERS)
        else:reply=client.put("/projects/p/environments/test",json=env,headers=HEADERS)
    elif operation=="contract_put":
        contract=client.get("/projects/p/contracts/c",headers=HEADERS).json();contract["expectations"]=[identical]
        reply=client.put("/projects/p/contracts/c",json=contract,headers=HEADERS)
    else:
        sc={"name":"other","prompt":{"template":"hi"},"contract":{"expectations":[identical]}}
        if operation=="scenario_post":reply=client.post("/projects/p/suites/s/scenarios",json=sc,headers=HEADERS)
        elif operation=="scenario_put":
            sc["name"]="a";reply=client.put("/projects/p/suites/s/scenarios/a",json=sc,headers=HEADERS)
        else:reply=client.post("/projects/p/suites",json={"name":"other","scenarios":[sc]},headers=HEADERS)
    assert reply.status_code==422 and "Independent Oracle" in reply.text,reply.text
    assert client.get("/projects/p",headers=HEADERS).json()==before
    assert calls==[]
