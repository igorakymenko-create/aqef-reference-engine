"""Reusable Contracts API endpoints.

References:
- Volume VII — Quality Contracts (§Reusable Contracts)
- Appendix A §A.5
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.5
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.contract import Contract
from engine.models.principal import Principal
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_contracts_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/contracts", tags=["Contracts"])

    @router.get("", response_model=List[Contract])
    def list_contracts(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_contracts(project)[offset:offset + limit]

    @router.post("", response_model=Contract, status_code=status.HTTP_201_CREATED)
    def create_contract(
        project: str,
        contract: Contract,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        if not contract.name:
            raise HTTPException(
                status_code=422,
                detail="Reusable Contract MUST have a 'name'",
            )

        # Governed by Approval Workflow under contract_define
        enforce_governed_contract_define(
            principal=current_user,
            project_name=project,
            target_resource=f"/projects/{project}/contracts/{contract.name}",
            storage=storage,
            approved_by=x_approved_by,
            external_review_reference=x_external_review_ref,
            details={"action": "contract_create", "contract_name": contract.name},
        )

        try:
            return storage.create_contract(project, contract)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.get("/{contract}", response_model=Contract)
    def get_contract(
        project: str,
        contract: str,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "read", storage)
        res = storage.get_contract(project, contract)
        if not res:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contract '{contract}' not found")
        return res

    @router.put("/{contract}", response_model=Contract)
    def update_contract(
        project: str,
        contract: str,
        updated: Contract,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        if not updated.name or updated.name != contract:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contract name in body must match path",
            )

        # Governed by Approval Workflow under contract_define
        enforce_governed_contract_define(
            principal=current_user,
            project_name=project,
            target_resource=f"/projects/{project}/contracts/{contract}",
            storage=storage,
            approved_by=x_approved_by,
            external_review_reference=x_external_review_ref,
            details={"action": "contract_update", "contract_name": contract},
        )

        try:
            return storage.update_contract(project, updated)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return router
