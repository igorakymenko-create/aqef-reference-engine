"""C.3 Decision resources and Result Resolution; no panel/control lifecycle."""
from copy import deepcopy
from functools import wraps
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, StrictStr

from engine.assessment import AssessmentEngine, result_base
from engine.auth import check_permission
from engine.decision import DecisionEngine, effective, find_clause, govern, identifier, now, result_state
from engine.models.base import AQEFBaseModel
from engine.models.principal import PrincipalKind
from engine.storage import StorageConflictError
from engine.validators import canonical
from engine.scoped import invalidators, review_route, qualifications_for, assess_expectation
import json


class BatchRequest(AQEFBaseModel):
    execution_batch_id: StrictStr = Field(min_length=1)


class SnapshotRequest(AQEFBaseModel):
    suites: list[StrictStr] = Field(min_length=1)
    environments: list[StrictStr] = Field(min_length=1)
    baselines: list[StrictStr] | None = None
    release_label: str | None = None


class OverrideRequest(BatchRequest):
    gate_result_id: StrictStr
    justification: StrictStr = Field(min_length=1)


class BaselineRequest(AQEFBaseModel):
    execution_id: StrictStr
    result_id: StrictStr
    name: StrictStr | None = None


class PolicyRequest(AQEFBaseModel):
    suites: list[StrictStr] = Field(min_length=1)
    environments: list[StrictStr] = Field(min_length=1)
    service_accounts: list[StrictStr] = Field(min_length=1)


class ReleaseRequest(BatchRequest):
    report_id: StrictStr
    snapshot_id: StrictStr
    decision: Literal["approved", "rejected", "overridden"]
    release_policy: StrictStr | None = None
    notes: str | None = None


class ReviewRequest(AQEFBaseModel):
    verdict: Literal["pass", "fail"]
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None
    supporting_evidence: object


class ReassessRequest(AQEFBaseModel):
    oracle: StrictStr


def get_decision_router(storage, principal_dep, provider):
    router = APIRouter(prefix="/projects/{project}", tags=["Decision and Release"])
    service = DecisionEngine(storage)

    def serialized(function):
        @wraps(function)
        def execute(*args, **kwargs):
            with storage.config_lock:
                return function(*args, **kwargs)
        return execute

    @router.post("/gates/check")
    @serialized
    def evaluate(project: str, request: BatchRequest, principal=Depends(principal_dep)):
        check_permission(principal, "execute", storage)
        return service.evaluate(project, request.execution_batch_id)

    @router.post("/snapshots", status_code=201)
    @serialized
    def snapshot(project: str, request: SnapshotRequest, principal=Depends(principal_dep)):
        check_permission(principal, "snapshot_create", storage)
        return service.snapshot(project, request.suites, request.environments, request.baselines, request.release_label)

    @router.post("/reports", status_code=201)
    @serialized
    def report(project: str, request: BatchRequest, principal=Depends(principal_dep)):
        check_permission(principal, "execute", storage)
        return service.report(project, request.execution_batch_id)

    @router.post("/gates/{gate}/override", status_code=201)
    @serialized
    def override(project: str, gate: str, request: OverrideRequest, principal=Depends(principal_dep)):
        check_permission(principal, "gate_override", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Gate override requires a Person")
        if not request.justification.strip():
            raise HTTPException(422, "Override justification must be nonempty")
        matches = [(e,g) for e in storage.decision_records("evaluation", project) for name,g in e["gates"].items()
                   if name == gate and g["id"] == request.gate_result_id and e["execution_batch_id"] == request.execution_batch_id]
        if not matches:
            raise HTTPException(404, "GateResult/Gate/batch combination not found")
        evaluation, result = matches[0]
        if result["status"] != "fail" or not result["blocking"]:
            raise HTTPException(409, "Only a failed blocking GateResult can be overridden")
        if storage.decision_record("override", project, result["id"]):
            raise HTTPException(409, "GateResult already overridden")
        snapshot = service.get("snapshot", project, evaluation["snapshot_id"])
        definition = next(g for g in snapshot["quality_gates"] if g["name"] == gate)
        if definition.get("override_requires"):
            check_permission(principal, definition["override_requires"], storage)
        meta, approval = govern(storage, principal, project, "gate_override", result["id"],
                                 {"execution_batch_id":request.execution_batch_id, "justification":request.justification}, True)
        return storage.save_decision("override", project, {"id":result["id"], "gate":gate,
            "execution_batch_id":request.execution_batch_id, "justification":request.justification,
            "approval_id":approval, **meta})

    @router.post("/baselines", status_code=201)
    def baseline(project: str, request: BaselineRequest, principal=Depends(principal_dep)):
        check_permission(principal, "baseline_approve", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Baseline approval requires a Person")
        record = storage.get_execution(project, request.execution_id)
        if record is None:
            raise HTTPException(404, "Execution not found")
        result = next((r for r in effective(storage.list_results(project, record["id"])) if r["id"] == request.result_id), None)
        if not result or result["disposition"] != "actionable" or invalidators(storage,project,result) or record["status"] != "completed":
            raise HTTPException(409, "Baseline requires an effective actionable Result of a completed Execution")
        if record["configuration"]["scenario"]["seeded_control"]:
            raise HTTPException(409, "Seeded Control cannot designate subject baseline")
        meta, approval = govern(storage, principal, project, "baseline_approve", request.execution_id, person_only=True)
        data = {"id":identifier(), "suite":record["suite"], "scenario":record["scenario"], "environment":record["environment"],
                "execution_id":record["id"], "result_id":result["id"], "result":result,
                "configuration":record["configuration"], "dataset":record["dataset"],
                "evidence":{"conversation":record["conversation"], "artifacts":record["artifacts"]},
                "approval_id":approval, **meta}
        if request.name is not None:
            data["name"] = request.name
        return storage.save_decision("baseline", project, data)

    @router.post("/release-policies", status_code=201)
    def policy(project: str, request: PolicyRequest, principal=Depends(principal_dep)):
        check_permission(principal, "release_decide", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Release Policy requires a Person")
        service.scope(project, request.suites, request.environments)
        for name in request.service_accounts:
            actor = storage.get_principal(name)
            if actor is None or actor.kind != PrincipalKind.SERVICE_ACCOUNT:
                raise HTTPException(422, "Policy service_accounts must name Service Accounts")
        meta, approval = govern(storage, principal, project, "release_decide", "release-policy", person_only=True)
        return storage.save_decision("policy", project, {"id":identifier(), "project":project,
            **request.model_dump(), **meta, "approval_id":approval})

    @router.post("/release-policies/{policy}/revoke")
    @serialized
    def revoke(project: str, policy: str, principal=Depends(principal_dep)):
        check_permission(principal, "release_decide", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Policy revocation requires a Person")
        data = service.get("policy", project, policy)
        if storage.decision_record("revocation", project, policy):
            raise HTTPException(409, "Policy is already revoked")
        _, approval = govern(storage, principal, project, "release_decide", policy, person_only=True)
        event = storage.save_decision("revocation", project, {"id":policy, "revoked_at":now(), "revoked_by":principal.id, "approval_id":approval})
        return data | {k:event[k] for k in ("revoked_at", "revoked_by")}

    @router.post("/releases", status_code=201)
    @serialized
    def release(project: str, request: ReleaseRequest, principal=Depends(principal_dep)):
        check_permission(principal, "release_decide", storage)
        records = service.batch(project, request.execution_batch_id)
        batch_info = service.batch_info(project, request.execution_batch_id)
        report = service.get("report", project, request.report_id)
        snapshot = service.get("snapshot", project, request.snapshot_id)
        if report.get("snapshot_id") != snapshot["id"] or report["scope"]["execution_batch_ids"] != [request.execution_batch_id]:
            raise HTTPException(409, "Report, Snapshot and batch must match")
        if not service.current(snapshot):
            raise HTTPException(409, "Scoped configuration changed since Snapshot")
        evaluations = [e for e in storage.decision_records("evaluation", project) if e["execution_batch_id"] == request.execution_batch_id]
        if not evaluations or evaluations[-1]["snapshot_id"] != snapshot["id"]:
            raise HTTPException(409, "Report must reference latest Gate evaluation")
        current_entries = service.entries(records, snapshot)
        if evaluations[-1]["result_state"] != result_state(current_entries):
            raise HTTPException(409, "Effective Results changed; evaluate Gates again")
        from engine.scoped import controls
        from engine.decision import digest
        if evaluations[-1].get("control_state",digest([]))!=digest(controls(storage,project,request.execution_batch_id)):
            raise HTTPException(409,"Seeded Control state changed; evaluate Gates again")
        if any(storage.is_admitted(project, oracle) != admitted for oracle, admitted in evaluations[-1]["admissions"].items()):
            raise HTTPException(409, "Judge Admission changed; evaluate Gates again")
        if not report["gates"] or set(report["gates"]) != {g["name"] for g in snapshot["quality_gates"]}:
            raise HTTPException(409, "Release requires every applicable Quality Gate and at least one")
        gates = service.overridden(project, evaluations[-1]["gates"])
        if report["gates"] != gates:
            raise HTTPException(409, "Generate a fresh Report after overrides")
        failures = [g for g in gates.values() if g["blocking"] and g["status"] == "fail"]
        if request.decision == "approved" and failures:
            raise HTTPException(409, "Approved Release requires every blocking Gate to pass")
        if request.decision == "overridden" and (not failures or any("override" not in g for g in failures)):
            raise HTTPException(409, "Overridden Release requires an override on every failed blocking GateResult")
        if principal.kind == PrincipalKind.SERVICE_ACCOUNT:
            if request.release_policy is None:
                raise HTTPException(403, "Service Account Release requires standing release_policy")
            policy = service.get("policy", project, request.release_policy)
            if storage.decision_record("revocation", project, policy["id"]) or principal.id not in policy["service_accounts"] or (
                batch_info["suite"] not in policy["suites"] or batch_info["environment"] not in policy["environments"]):
                raise HTTPException(403, "Release Policy is revoked or does not cover actor/scope")
            if request.decision == "overridden" or (request.decision == "approved" and any("override" in g for g in gates.values() if g["blocking"])):
                raise HTTPException(403, "Service Account cannot authorize overridden Release")
        elif request.release_policy is not None:
            raise HTTPException(422, "release_policy is for Service Account decisions")
        meta, approval = govern(storage, principal, project, "release_decide", request.report_id,
                                 {"release_policy":request.release_policy, "decision":request.decision})
        data = {"id":identifier(), "project":project, "suite":batch_info["suite"], "environment":batch_info["environment"],
                **request.model_dump(exclude_none=True), "gates":gates, **meta, "approval_id":approval}
        return storage.save_decision("release", project, data)

    def result_context(project, execution, key):
        record = storage.get_execution(project, execution)
        if record is None:
            raise HTTPException(404, "Execution not found")
        rows = storage.list_results(project, execution)
        row = next((r for r in rows if r["id"] == key), None)
        if row is None:
            raise HTTPException(404, "Result not found")
        if key not in {r["id"] for r in effective(rows)} or (row["disposition"] == "actionable" and not invalidators(storage,project,row)):
            raise HTTPException(409, "Only current non-actionable effective Result may be resolved")
        return record, row, find_clause(record, row["clause"])

    @router.post("/executions/{execution}/results/{result}/review", status_code=201)
    def review(project: str, execution: str, result: str, request: ReviewRequest, principal=Depends(principal_dep)):
        check_permission(principal, "review", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Human Review requires a Person")
        record, previous, clause = result_context(project, execution, result)
        if invalidators(storage,project,previous) and not (previous["oracle_type"]=="human_reviewer" and previous["disposition"]=="awaiting_review"):
            raise HTTPException(409,"Invalidated instruments require requalification, not ordinary review")
        if previous["disposition"] not in ("inconclusive", "awaiting_review"):
            raise HTTPException(409, "This Result is not open to Human Review resolution")
        human = clause.get("human_reviewer") or {}
        route=review_route(previous)
        role=route["role"] if route else human.get("role")
        captures=route["captures_confidence"] if route else human.get("captures_confidence",False)
        if role and role not in principal.roles:
            raise HTTPException(403, "Reviewer lacks clause's required Role")
        if human.get("role") and role!=human["role"] and (not route or route["state"]!="escalated") and human["role"] not in principal.roles:
            raise HTTPException(403,"Corrected Human Oracle does not waive the frozen clause's policy Role")
        if "confidence" in request.model_fields_set and request.confidence is None:
            raise HTTPException(422, "Omit uncaptured Confidence; never supply null")
        if captures and request.confidence is None:
            raise HTTPException(422, "This review requires Confidence")
        if human and not captures and request.confidence is not None:
            raise HTTPException(422,"This Human Reviewer does not capture Confidence")
        confidence = request.confidence if request.confidence is not None else "not_applicable"
        disposition = "inconclusive" if request.confidence is not None and request.confidence < (clause.get("confidence_threshold") or 0) else "actionable"
        evidence = {"reviewer":principal.id, "reviewed_at":now(), "evidence":request.supporting_evidence}
        if previous["disposition"] == "awaiting_review" and previous["oracle_type"]=="human_reviewer":
            completed = deepcopy(previous)
            completed.update(verdict=request.verdict, confidence=confidence, disposition=disposition, supporting_evidence={**previous["supporting_evidence"],**evidence,"reviewed_route":route})
            return storage.complete_review(project, completed)
        data = result_base(record, previous["clause"], "human_reviewer",
                           canonical({"type":"human_reviewer", "role":human.get("role", "review"), "version":"1"}), evidence)
        data.update(verdict=request.verdict, confidence=confidence, disposition=disposition, resolves=previous["id"])
        try:
            return storage.append_result(project, data)
        except StorageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/executions/{execution}/results/{result}/reassess", status_code=201)
    async def reassess(project: str, execution: str, result: str, request: ReassessRequest, principal=Depends(principal_dep)):
        check_permission(principal, "execute", storage)
        record, previous, clause = result_context(project, execution, result)
        same=previous["oracle"]==request.oracle
        if same and (previous["disposition"]!="oracle_unavailable" or invalidators(storage,project,previous)):
            raise HTTPException(409,"Same Oracle may only recover uninvalidated oracle_unavailable")
        seen=previous["supporting_evidence"].get("provider_response",{})
        if same and isinstance(seen,dict) and seen.get("verdict") in ("pass","fail"):
            raise HTTPException(409,"A received verdict cannot be retried away despite malformed Confidence/protocol")
        members=previous["supporting_evidence"].get("member_results",[])
        if same and members and not any(m["disposition"]=="oracle_unavailable" and
            (not isinstance(m["supporting_evidence"].get("provider_response"),dict) or
             m["supporting_evidence"]["provider_response"].get("verdict") not in ("pass","fail")) for m in members):
            raise HTTPException(409,"No panel member can be re-attempted before a verdict; received verdicts stand")
        exemptions=previous["supporting_evidence"].get("requalified_controls",[]) if same else qualifications_for(storage,record,previous,request.oracle)
        try:config=json.loads(request.oracle)
        except ValueError as exc:raise HTTPException(422,"Oracle must be an inspectable canonical configuration") from exc
        corrected=deepcopy(clause)
        working=deepcopy(record)
        if not same:
            if config.get("type")=="validator" and previous["oracle_type"]=="validator":
                if (config["target"],config["expected"])!=(clause["target"],clause["expected"]):
                    raise HTTPException(409,"Reassessment cannot change the frozen clause's target or expected requirement")
                corrected.update(validator=config["name"],target=config["target"],expected=config["expected"])
                if config.get("custom"):working["configuration"]["validators"][config["name"]]=config["custom"]
            elif config.get("type")=="judge" and previous["oracle_type"]!="validator":
                if clause.get("multi_judge") or clause.get("human_reviewer") or config["criteria"]!=clause["criteria"]:
                    raise HTTPException(409,"Corrected Judge must preserve the frozen clause criteria and Oracle architecture")
                corrected.update(judge={"model":config["model"],"confidence_source":config["confidence_source"]},multi_judge=None,human_reviewer=None,criteria=config["criteria"])
            elif config.get("type")=="multi_judge" and previous["oracle_type"]!="validator":
                original=clause.get("multi_judge")
                new=config["configuration"]
                if original is None or config["criteria"]!=clause["criteria"] or any(original.get(k)!=new.get(k) for k in ("purpose","consensus","samples")) or len(original.get("judges") or [original.get("judge")])!=len(new.get("judges") or [new.get("judge")]):
                    raise HTTPException(409,"Corrected panel must preserve criteria, purpose, count and Consensus/quorum requirements")
                corrected.update(judge=None,multi_judge=config["configuration"],human_reviewer=None,criteria=config["criteria"])
            elif config.get("type")=="human_reviewer" and previous["oracle_type"]=="human_reviewer":
                corrected["human_reviewer"]={**(clause.get("human_reviewer") or {}),"role":config["role"]}
            else:raise HTTPException(409,"Corrected Oracle must have a compatible executable Oracle type")
        assessment = AssessmentEngine(storage, provider)
        try:
            if previous["oracle_type"] == "validator":
                new=assessment.validate(working,corrected,previous["clause"],persist=False)
                if new["oracle"]!=request.oracle:raise HTTPException(409,"Corrected Validator identity/version mismatch")
                new["resolves"]=previous["id"]
                if exemptions:new["supporting_evidence"]["requalified_controls"]=exemptions
                return storage.append_result(project,new)
            if previous["oracle_type"] == "judge":
                from engine.assessment import judge_identity
                from engine.scoped import panel_identity
                identity=judge_identity(corrected) if corrected.get("judge") else panel_identity(corrected)
                if identity!=request.oracle:raise HTTPException(409,"Corrected Judge identity/version mismatch")
                judges=[corrected["judge"]] if corrected.get("judge") else corrected["multi_judge"].get("judges") or [corrected["multi_judge"]["judge"]]
                if any(j["model"].strip().lower()==record["configuration"]["environment"]["model_version"].strip().lower() for j in judges):
                    raise HTTPException(422,"Corrected Judge must remain independent of subject")
                return await assess_expectation(assessment,working,corrected,previous["clause"],previous["id"],exemptions,
                                                previous["supporting_evidence"].get("member_results") if same else None)
            if previous["oracle_type"]=="human_reviewer" and not same:
                from engine.scoped import pending_review
                return pending_review(storage,working,corrected,previous["clause"],previous["id"],exemptions)
        except StorageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        raise HTTPException(409, "Human Reviewer unavailability cannot be reassessed as an automated Oracle")

    # Identical read/pagination conventions for append-only decision collections.
    def read_collection(kind):
        def endpoint(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                     principal=Depends(principal_dep)):
            check_permission(principal, "read", storage)
            records = storage.decision_records(kind, project)
            if not records and storage.get_project(project) is None:
                raise HTTPException(404, "Project not found")
            if kind == "policy":
                records = [decorate_policy(project, r) for r in records]
            return records[offset:offset+limit]
        return endpoint

    def decorate_policy(project, data):
        event = storage.decision_record("revocation", project, data["id"])
        return data | ({k:event[k] for k in ("revoked_at", "revoked_by")} if event else {})

    def read_one(kind):
        def endpoint(project: str, key: str, principal=Depends(principal_dep)):
            check_permission(principal, "read", storage)
            data = service.get(kind, project, key)
            return decorate_policy(project, data) if kind == "policy" else data
        return endpoint

    for path, kind in (("snapshots","snapshot"), ("baselines","baseline"), ("reports","report"),
                       ("releases","release"), ("release-policies","policy")):
        router.add_api_route("/" + path, read_collection(kind), methods=["GET"], name="list_" + path)
        router.add_api_route("/" + path + "/{key}", read_one(kind), methods=["GET"], name="get_" + path)
    return router
