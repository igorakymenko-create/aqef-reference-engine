"""Authentication and authorization system.

References:
- Volume XII — Governance (§Principals, §Roles, §Permissions, §Approval Workflow, §Audit)
- Appendix C §C.4 (Authentication and Authorization)
- Appendix C §C.5 (Governance Side Effects)
"""

import uuid
from typing import Callable, List, Optional, Set
from fastapi import Depends, Header, HTTPException, status
from engine.models.principal import (
    ApprovalRecord,
    ApprovalStatus,
    AuditLogEntry,
    Principal,
    PrincipalKind,
)
from engine.storage import Storage
from engine.audit import checked_permission


def get_current_principal_dependency(storage_getter: Callable[[], Storage]):
    """FastAPI dependency for resolving authenticated Principal from Bearer token."""

    def _dependency(authorization: Optional[str] = Header(None)) -> Principal:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected 'Bearer <token>'",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = parts[1]
        storage = storage_getter()
        principal = storage.get_principal_by_token(token)
        if not principal:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unrecognized Bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return principal

    return _dependency


def get_principal_permissions(principal: Principal, storage: Storage) -> Set[str]:
    """Resolve all permissions for a principal across their assigned roles."""
    permissions: Set[str] = set()
    for role_name in principal.roles:
        # "admin" role or permission grants full privileges
        if role_name == "admin":
            permissions.add("admin")
        role = storage.get_role(role_name)
        if role:
            permissions.update(role.permissions)
    return permissions


def check_permission(principal: Principal, permission: str, storage: Storage) -> None:
    """Check that the principal holds the required atomic permission."""
    perms = get_principal_permissions(principal, storage)
    if "admin" in perms:
        checked_permission(principal, permission, storage)
        return
    if permission not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Principal '{principal.id}' lacks required permission: '{permission}'",
        )
    checked_permission(principal, permission, storage)


def enforce_governed_contract_define(
    principal: Principal,
    project_name: str,
    target_resource: str,
    storage: Storage,
    external_review_reference: Optional[str] = None,
    approved_by: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Enforce Volume XII and Appendix C §C.5 rules for `contract_define` action.

    Rules:
    - Principal MUST hold `contract_define` permission.
    - If Principal is Person: records approval by that Person.
    - If Principal is Service Account: MUST have approved_by naming a Person and external_review_reference.
    - Creates an ApprovalRecord and an AuditLogEntry.
    """
    check_permission(principal, "contract_define", storage)

    actual_approved_by: Optional[str] = None
    if principal.kind == PrincipalKind.PERSON:
        actual_approved_by = principal.id
    elif principal.kind == PrincipalKind.SERVICE_ACCOUNT:
        # Volume XII — Principals:
        # "contract_define MAY be applied by a Service Account when the change was approved by a
        # Person in an external review... The Approval Workflow record MUST name that Person and reference the review."
        if not approved_by or not external_review_reference:
            raise HTTPException(
                status_code=422,
                detail=(
                    "A Service Account applying 'contract_define' MUST supply 'approved_by' (naming a Person) "
                    "and 'external_review_reference'"
                ),
            )
        # Verify approved_by exists and is a Person
        approver = storage.get_principal(approved_by)
        if not approver or approver.kind != PrincipalKind.PERSON:
            raise HTTPException(
                status_code=422,
                detail=f"Approved_by '{approved_by}' must resolve to an existing Person principal",
            )
        actual_approved_by = approved_by

    # Create ApprovalRecord
    approval = ApprovalRecord(
        id=str(uuid.uuid4()),
        project=project_name,
        action="contract_define",
        target_resource=target_resource,
        requested_by=principal.id,
        approved_by=actual_approved_by,
        status=ApprovalStatus.APPROVED,
        external_review_reference=external_review_reference,
        details=details or {},
    )
    storage.create_approval(approval)

    # Create AuditLogEntry
    audit = AuditLogEntry(
        id=str(uuid.uuid4()),
        project=project_name,
        action="contract_define",
        principal_id=principal.id,
        principal_kind=principal.kind,
        details={"target": target_resource, "approval_id": approval.id, **(details or {})},
    )
    storage.create_audit_entry(audit)
