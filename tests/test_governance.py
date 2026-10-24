"""Tests for Governance, Authentication, and Permissions.

Section references:
- Volume XII — Governance (§Teams, §Roles, §Permissions, §Principals, §Approval Workflow, §Audit)
- Appendix C §C.4 (Authentication and Authorization)
- Appendix C §C.5 (Governance Side Effects)
"""

import pytest
from pydantic import ValidationError
from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.principal import Principal, PrincipalKind, Role, Team
from engine.storage import Storage


def test_service_account_requires_owning_person():
    # Volume XII — Principals:
    # "A Service Account... MUST have an owning Person accountable for what it does."
    with pytest.raises(ValidationError) as exc:
        Principal(
            id="svc-ci",
            kind=PrincipalKind.SERVICE_ACCOUNT,
            name="CI Bot",
            owner_person_id=None,
        )
    assert "owner_person_id is required" in str(exc.value)


def test_person_must_not_have_owning_person():
    # Volume XII — Principals:
    # "A Service Account is not a stand-in for a person and MUST NOT be set up to look like one."
    with pytest.raises(ValidationError) as exc:
        Principal(
            id="person-alice",
            kind=PrincipalKind.PERSON,
            name="Alice",
            owner_person_id="someone-else",
        )
    assert "A Person MUST NOT have an owner_person_id" in str(exc.value)


def test_permission_checked_independently_of_role():
    # Volume XII — Permissions:
    # "A Permission MUST be checkable independently of any Role that happens to include it...
    # a Role is a convenience for assignment, not the unit Governance actually enforces."
    storage = Storage(db_path=":memory:")
    author_role = Role(name="contract_author", permissions=["contract_define", "read"])
    storage.create_role(author_role)

    alice = Principal(
        id="alice",
        kind=PrincipalKind.PERSON,
        name="Alice",
        roles=["contract_author"],
    )
    storage.create_principal(alice, token="alice-token")

    # Alice has contract_define
    check_permission(alice, "contract_define", storage)
    check_permission(alice, "read", storage)

    # Alice lacks project_create
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        check_permission(alice, "project_create", storage)
    assert exc.value.status_code == 403


def test_contract_define_governed_for_person():
    # Volume XII — Approval Workflow; Appendix C §C.5:
    # Defining a contract by a Person logs an ApprovalRecord and an AuditLogEntry.
    storage = Storage(db_path=":memory:")
    storage.create_role(Role(name="author", permissions=["contract_define"]))
    alice = Principal(id="alice", kind=PrincipalKind.PERSON, name="Alice", roles=["author"])
    storage.create_principal(alice, token="alice-token")

    enforce_governed_contract_define(
        principal=alice,
        project_name="proj-alpha",
        target_resource="/projects/proj-alpha/contracts/safety",
        storage=storage,
    )

    approvals = storage.list_approvals("proj-alpha")
    assert len(approvals) == 1
    assert approvals[0].action == "contract_define"
    assert approvals[0].requested_by == "alice"
    assert approvals[0].approved_by == "alice"

    audit = storage.list_audit_logs("proj-alpha")
    assert len(audit) == 1
    assert audit[0].action == "contract_define"
    assert audit[0].principal_id == "alice"


def test_contract_define_by_service_account_requires_person_and_review_ref():
    # Volume XII — Principals:
    # "contract_define MAY be applied by a Service Account when the change was approved by a
    # Person in an external review... The Approval Workflow record MUST name that Person and reference the review."
    storage = Storage(db_path=":memory:")
    storage.create_role(Role(name="ci_role", permissions=["contract_define"]))
    alice = Principal(id="alice", kind=PrincipalKind.PERSON, name="Alice", roles=["ci_role"])
    storage.create_principal(alice, token="alice-token")

    bot = Principal(
        id="bot",
        kind=PrincipalKind.SERVICE_ACCOUNT,
        name="CI Runner",
        owner_person_id="alice",
        roles=["ci_role"],
    )
    storage.create_principal(bot, token="bot-token")

    from fastapi import HTTPException

    # Missing external review reference and approved_by
    with pytest.raises(HTTPException) as exc:
        enforce_governed_contract_define(
            principal=bot,
            project_name="proj-beta",
            target_resource="/projects/proj-beta/contracts/safety",
            storage=storage,
            approved_by=None,
            external_review_reference=None,
        )
    assert exc.value.status_code == 422
    assert "approved_by" in exc.value.detail

    # Supplying valid person approver and review reference succeeds
    enforce_governed_contract_define(
        principal=bot,
        project_name="proj-beta",
        target_resource="/projects/proj-beta/contracts/safety",
        storage=storage,
        approved_by="alice",
        external_review_reference="PR #42 in github.com/corp/contracts",
    )

    approvals = storage.list_approvals("proj-beta")
    assert len(approvals) == 1
    assert approvals[0].requested_by == "bot"
    assert approvals[0].approved_by == "alice"
    assert approvals[0].external_review_reference == "PR #42 in github.com/corp/contracts"
