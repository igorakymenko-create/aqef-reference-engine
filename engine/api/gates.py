"""Quality Gates API endpoints.

References:
- Volume I, Chapter 6 — Aggregate Basis and Quality Gates
- Appendix A §A.10
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.5
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.gate import QualityGate
from engine.models.principal import Principal
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_gates_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/gates", tags=["Quality Gates"])

    @router.get("", response_model=List[QualityGate])
    def list_quality_gates(project: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_quality_gates(project)

    @router.post("", response_model=QualityGate, status_code=status.HTTP_201_CREATED)
    def create_quality_gate(
        project: str,
        gate: QualityGate,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        # Governed by Approval Workflow under contract_define
        enforce_governed_contract_define(
            principal=current_user,
            project_name=project,
            target_resource=f"/projects/{project}/gates/{gate.name}",
            storage=storage,
            approved_by=x_approved_by,
            external_review_reference=x_external_review_ref,
            details={"action": "gate_create", "gate_name": gate.name},
        )

        try:
            return storage.create_quality_gate(project, gate)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.put("/{gate}", response_model=QualityGate)
    def update_quality_gate(
        project: str,
        gate: str,
        updated: QualityGate,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        if updated.name != gate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quality Gate name in body must match path",
            )

        # Governed by Approval Workflow under contract_define
        enforce_governed_contract_define(
            principal=current_user,
            project_name=project,
            target_resource=f"/projects/{project}/gates/{gate}",
            storage=storage,
            approved_by=x_approved_by,
            external_review_reference=x_external_review_ref,
            details={"action": "gate_update", "gate_name": gate},
        )

        try:
            return storage.update_quality_gate(project, updated)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return router
