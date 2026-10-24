"""C.3 seeded-control confirmation, invalidation and requalification."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, StrictStr, StrictBool, field_validator
from datetime import datetime

from engine.auth import check_permission
from engine.decision import identifier, now
from engine.models.base import AQEFBaseModel
from engine.models.principal import PrincipalKind, AuditLogEntry
from engine.scoped import controls, lookup_result, scored_at


class ConfirmRequest(AQEFBaseModel):
    confirmed: StrictBool
    supporting_evidence: object

    @field_validator("confirmed")
    @classmethod
    def affirmative(cls,value):
        if not value:raise ValueError("Only actual affirmative confirmation may be recorded")
        return value


class InvalidateRequest(AQEFBaseModel):
    reason: StrictStr = Field(min_length=1)


class RequalificationRequest(AQEFBaseModel):
    oracle: StrictStr
    defect_class: StrictStr = Field(min_length=1)
    controls: list[StrictStr] = Field(min_length=1)
    diagnosis: str | None = None


def get_scoped_router(store, principal_dep):
    router=APIRouter(prefix="/projects/{project}",tags=["Scoped capabilities"])

    def control_for(project,execution,scenario):
        record=store.get_execution(project,execution)
        if record is None:raise HTTPException(404,"Execution not found")
        candidates=[c for c in controls(store,project,record["execution_batch_id"]) if c["scenario"]==scenario]
        if not candidates:raise HTTPException(404,"Seeded Control not found in this run")
        return candidates[0]

    @router.post("/executions/{execution}/seeded-controls/{scenario}/confirm",status_code=201)
    def confirm(project:str,execution:str,scenario:str,request:ConfirmRequest,principal=Depends(principal_dep)):
        check_permission(principal,"review",store)
        if principal.kind!=PrincipalKind.PERSON:raise HTTPException(403,"Control confirmation requires a Person")
        with store.config_lock:
            c=control_for(project,execution,scenario)
            if c["confirmed_by"]!="human_reviewer" and not c.get("needs_reference_review"):
                raise HTTPException(409,"This control does not require Human confirmation")
            if not c["assessments"]:raise HTTPException(409,"No control Evidence was assessed")
            event={"id":c["id"],"confirmed_by":principal.id,"recorded_at":now(),"supporting_evidence":request.supporting_evidence}
            store.save_decision("control_confirmation",project,event)
            store.create_audit_entry(AuditLogEntry(id=identifier(),project=project,action="seeded_control_confirm",
                principal_id=principal.id,principal_kind=principal.kind,details={"control_id":c["id"]}))
            return control_for(project,execution,scenario)

    @router.post("/executions/{execution}/seeded-controls/{scenario}/invalidate",status_code=201)
    def invalidate(project:str,execution:str,scenario:str,request:InvalidateRequest,principal=Depends(principal_dep)):
        check_permission(principal,"seeded_control_invalidate",store)
        if not request.reason.strip():raise HTTPException(422,"Full-run invalidation reason must be nonempty")
        with store.config_lock:
            c=control_for(project,execution,scenario)
            if c["outcome"] not in ("missed","false_alarm"):raise HTTPException(409,"Only a missed control may invalidate the full run")
            if c["invalidation_scope"]=="full_run":raise HTTPException(409,"Run already invalidated for this control")
            event={"id":c["id"],"reason":request.reason,"recorded_at":now(),"recorded_by":principal.id}
            store.save_decision("full_invalidation",project,event)
            store.create_audit_entry(AuditLogEntry(id=identifier(),project=project,action="seeded_control_invalidate",
                principal_id=principal.id,principal_kind=principal.kind,details=event))
            return control_for(project,execution,scenario)

    @router.post("/requalifications",status_code=201)
    def requalify(project:str,request:RequalificationRequest,principal=Depends(principal_dep)):
        check_permission(principal,"execute",store)
        if store.get_project(project) is None:raise HTTPException(404,"Project not found")
        with store.config_lock:
            known=controls(store,project)
            misses=[c for c in known if c["defect_class"]==request.defect_class and c["outcome"] in ("missed","false_alarm")]
            for key in request.controls:
                row=lookup_result(store,project,key)
                c=next((c for c in known if key in c["assessments"]),None)
                if row is None or c is None or c["defect_class"]!=request.defect_class or row["oracle"]!=request.oracle:
                    raise HTTPException(422,"Qualification must name stored control Results of the same Oracle and class")
                if not any(o["oracle"]==request.oracle and key in o["result_ids"] and o["outcome"] in ("caught","passed") for o in c["oracles"]):
                    raise HTTPException(422,"Qualification control must be confirmed caught/passed by this Oracle")
                if any((m["suite"],m["scenario"])==(c["suite"],c["scenario"]) or
                    (m.get("source_execution") and m.get("source_execution")==c.get("source_execution")) or
                    m.get("evidence_fingerprint")==c.get("evidence_fingerprint") for m in misses):
                    raise HTTPException(409,"Qualification control is exposed by a miss or false alarm")
                if any(datetime.fromisoformat(scored_at(row))<=datetime.fromisoformat(m.get("miss_recorded_at",m["recorded_at"])) for m in misses):
                    raise HTTPException(409,"Qualification controls must be fresh after the diagnosed misses")
            data={"id":identifier(),**request.model_dump(exclude_none=True),"recorded_at":now(),"recorded_by":principal.id}
            return store.save_decision("requalification",project,data)

    @router.get("/requalifications")
    def requalifications(project:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000),principal=Depends(principal_dep)):
        check_permission(principal,"read",store)
        return store.decision_records("requalification",project)[offset:offset+limit]
    return router
