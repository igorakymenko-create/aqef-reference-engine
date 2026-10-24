"""Project API endpoints.

References:
- Volume II — Domain Model (§Project)
- Appendix A §A.1
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.5, §C.8
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.principal import Principal
from engine.models.project import Project
from engine.storage import Storage, StorageConflictError, StorageNotFoundError
from engine.validation import ConfigurationValidationError, validate_project_configuration
from engine.audit import bind_project


def has_governed_definitions(project):
    return bool(project.contracts or project.quality_gates or any(
        suite.contracts or suite.quality_gates or any(sc.contract is not None for sc in suite.scenarios)
        for suite in project.suites))


def get_projects_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["Projects"])

    @router.get("", response_model=List[Project])
    def list_projects(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_projects()[offset:offset + limit]

    @router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(
        project: Project,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "project_create", storage)
        bind_project(project.name)

        # Validate complete configuration
        try:
            validate_project_configuration(
                project,
                lookup_reusable_contract=lambda name: storage.get_contract(project.name, name),
                lookup_dataset=lambda name, ver: storage.get_dataset(project.name, name, ver),
            )
        except (ConfigurationValidationError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Appendix C §C.5: Governed configuration change
        # If project contains contracts or quality_gates, governance contract_define applies
        if has_governed_definitions(project):
            enforce_governed_contract_define(
                principal=current_user,
                project_name=project.name,
                target_resource=f"/projects/{project.name}",
                storage=storage,
                approved_by=x_approved_by,
                external_review_reference=x_external_review_ref,
                details={"action": "project_create_with_contracts_or_gates"},
            )

        try:
            return storage.create_project(project)
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.get("/{project}", response_model=Project)
    def get_project(project: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        proj = storage.get_project(project)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project}' not found")
        return proj

    @router.put("/{project}", response_model=Project)
    def update_project(
        project: str,
        updated: Project,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "project_edit", storage)
        if updated.name != project:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project name in body must match path")
        current = storage.get_project(project)
        if current is None:
            raise HTTPException(404, f"Project '{project}' not found")

        try:
            validate_project_configuration(
                updated,
                lookup_reusable_contract=lambda name: storage.get_contract(project, name),
                lookup_dataset=lambda name, ver: storage.get_dataset(project, name, ver),
            )
        except (ConfigurationValidationError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

        # Appendix C §C.5: contract_define governance
        if has_governed_definitions(updated) or has_governed_definitions(current):
            enforce_governed_contract_define(
                principal=current_user,
                project_name=project,
                target_resource=f"/projects/{project}",
                storage=storage,
                approved_by=x_approved_by,
                external_review_reference=x_external_review_ref,
                details={"action": "project_put_with_contracts_or_gates"},
            )

        try:
            return storage.update_project(updated)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.delete("/{project}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_project(
        project: str,
        retain_history: bool = Query(False),
        current_user: Principal = Depends(get_principal_dep),
    ):
        # Appendix C §C.8: Deletion referential integrity
        check_permission(current_user, "project_delete", storage)
        try:
            storage.delete_project(project, retain_history=retain_history)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return router
