"""Admission and declarative Custom Validator definition APIs."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.assessment import AdmissionRequest
from engine.models.principal import PrincipalKind
from engine.storage import StorageConflictError
from engine.validators import CustomValidator


def get_assessment_router(storage, principal_dep):
    router = APIRouter(prefix="/projects/{project}", tags=["Assessment"])

    def require_project(project):
        if storage.get_project(project) is None:
            raise HTTPException(404, "Project not found")

    @router.post("/admissions", status_code=201)
    def admit(project: str, request: AdmissionRequest, principal=Depends(principal_dep)):
        check_permission(principal, "review", storage)
        if principal.kind != PrincipalKind.PERSON:
            raise HTTPException(403, "Only a Person may record Admission")
        require_project(project)
        for reviewer in request.labelled_by:
            person = storage.get_principal(reviewer)
            if not person or person.kind != PrincipalKind.PERSON:
                raise HTTPException(422, "labelled_by must name existing Person principals")
        data = request.model_dump(mode="json", exclude_unset=True)
        data.update(id=str(uuid.uuid4()), recorded_at=datetime.now(timezone.utc).isoformat(), recorded_by=principal.id)
        return storage.append_admission(project, data)

    @router.get("/admissions")
    def admissions(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                   oracle: str | None = None, principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        rows = storage.list_admissions(project)
        if not rows:
            require_project(project)
        return [r for r in rows if oracle is None or r["oracle"] == oracle][offset:offset + limit]

    @router.post("/validators", status_code=201)
    def register(project: str, request: CustomValidator, principal=Depends(principal_dep),
                 x_approved_by: str | None = Header(None, alias="X-Approved-By"),
                 x_external_review_ref: str | None = Header(None, alias="X-External-Review-Ref")):
        check_permission(principal, "contract_define", storage)
        require_project(project)
        try:
            request.validate_rule()
        except Exception as exc:
            raise HTTPException(422, str(exc)) from exc
        if any(r["name"] == request.name and r["version"] == request.version for r in storage.list_custom_validators(project)):
            raise HTTPException(409, "Custom Validator name@version is immutable")
        enforce_governed_contract_define(principal, project, f"validators/{request.name}@{request.version}", storage,
                                        approved_by=x_approved_by, external_review_reference=x_external_review_ref)
        try:
            return storage.create_custom_validator(project, request.model_dump(mode="json"))
        except StorageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/validators")
    def validators(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                   principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        require_project(project)
        return storage.list_custom_validators(project)[offset:offset + limit]

    return router
