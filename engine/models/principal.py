"""Principals, Teams, Roles, Permissions, Approvals, and Audit models.

References:
- Volume XII — Governance (§Teams, §Roles, §Permissions, §Principals, §Approval Workflow, §Audit)
- Appendix C §C.4 (Authentication and Authorization)
- Appendix B §B.2, §B.3
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from engine.models.base import AQEFBaseModel


class PrincipalKind(str, Enum):
    PERSON = "person"
    SERVICE_ACCOUNT = "service_account"


class Team(AQEFBaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: Optional[str] = None


class Role(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    permissions: List[str] = Field(default_factory=list)


class Principal(AQEFBaseModel):
    id: str = Field(..., min_length=1)
    kind: PrincipalKind
    name: str = Field(..., min_length=1)
    email: Optional[str] = None
    team_ids: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    owner_person_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_owner_person(self) -> "Principal":
        # Volume XII — Principals:
        # A Service Account MUST have an owning Person accountable for what it does.
        # A Service Account is not a stand-in for a person and MUST NOT be set up to look like one.
        if self.kind == PrincipalKind.SERVICE_ACCOUNT:
            if not self.owner_person_id or not self.owner_person_id.strip():
                raise ValueError("A Service Account MUST have an owning Person accountable for what it does (owner_person_id is required)")
        elif self.kind == PrincipalKind.PERSON:
            if self.owner_person_id:
                raise ValueError("A Person MUST NOT have an owner_person_id")
        return self


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class ApprovalRecord(BaseModel):
    id: str = Field(..., min_length=1)
    project: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    target_resource: str = Field(..., min_length=1)
    requested_by: str = Field(..., min_length=1)
    approved_by: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.APPROVED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    external_review_reference: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class AuditLogEntry(BaseModel):
    id: str = Field(..., min_length=1)
    project: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    principal_id: str = Field(..., min_length=1)
    principal_kind: PrincipalKind
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict)
