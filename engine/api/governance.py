"""Governance endpoints: Teams, Roles, Principals, Audit Logs, and Approvals.

References:
- Volume XII — Governance
- Appendix C §C.3 (Governance resources)
- Appendix C §C.4 (Authentication and Authorization)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from engine.auth import check_permission
from engine.models.principal import (
    ApprovalRecord,
    AuditLogEntry,
    Principal,
    PrincipalKind,
    Role,
    Team,
)
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


class PrincipalCreateRequest(Principal):
    id: str = Field(..., min_length=1)
    kind: PrincipalKind
    name: str = Field(..., min_length=1)
    email: Optional[str] = None
    team_ids: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    owner_person_id: Optional[str] = None
    token: Optional[str] = None


def get_governance_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(tags=["Governance"])

    # --- Teams ---

    @router.get("/teams", response_model=List[Team])
    def list_teams(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "team_read", storage)
        return storage.list_teams()[offset:offset + limit]

    @router.post("/teams", response_model=Team, status_code=status.HTTP_201_CREATED)
    def create_team(team: Team, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "team_admin", storage)
        try:
            return storage.create_team(team)
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # --- Roles ---

    @router.get("/roles", response_model=List[Role])
    def list_roles(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "role_read", storage)
        return storage.list_roles()[offset:offset + limit]

    @router.post("/roles", response_model=Role, status_code=status.HTTP_201_CREATED)
    def create_role(role: Role, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "role_admin", storage)
        try:
            return storage.create_role(role)
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # --- Principals Management ---

    @router.post("/principals", response_model=Principal, status_code=status.HTTP_201_CREATED)
    def create_principal(
        req: PrincipalCreateRequest,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "role_admin", storage)
        if req.kind == PrincipalKind.SERVICE_ACCOUNT:
            owner = storage.get_principal(req.owner_person_id)
            if owner is None or owner.kind != PrincipalKind.PERSON:
                raise HTTPException(422, "owner_person_id must name an existing Person")
        p = Principal(
            id=req.id,
            kind=req.kind,
            name=req.name,
            email=req.email,
            team_ids=req.team_ids,
            roles=req.roles,
            owner_person_id=req.owner_person_id,
        )
        try:
            return storage.create_principal(p, token=req.token or req.id)
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # --- Audit Logs & Approvals ---

    @router.get("/projects/{project}/audit", response_model=List[AuditLogEntry])
    def get_audit_log(
        project: str,
        action: Optional[str] = Query(None),
        principal_id: Optional[str] = Query(None),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "audit_read", storage)
        return storage.list_audit_logs(project, action=action, principal_id=principal_id)[offset:offset + limit]

    @router.get("/projects/{project}/approvals", response_model=List[ApprovalRecord])
    def get_approvals(
        project: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "audit_read", storage)
        return storage.list_approvals(project)[offset:offset + limit]

    return router
