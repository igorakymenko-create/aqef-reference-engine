"""Suites and Scenarios API endpoints.

References:
- Volume II — Domain Model (§Suite, §Scenario)
- Appendix A §A.3, §A.4
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.5, §C.8
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from engine.auth import check_permission, enforce_governed_contract_define
from engine.models.principal import Principal
from engine.models.scenario import Scenario
from engine.models.suite import Suite
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_suites_scenarios_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/suites", tags=["Suites and Scenarios"])

    # --- Suites ---

    @router.get("", response_model=List[Suite])
    def list_suites(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_suites(project)[offset:offset + limit]

    @router.post("", response_model=Suite, status_code=status.HTTP_201_CREATED)
    def create_suite(
        project: str,
        suite: Suite,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "suite_create", storage)

        # Check gate uniqueness against Project
        proj = storage.get_project(project)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project}' not found")

        project_gate_names = {g.name for g in proj.quality_gates}
        for g in suite.quality_gates:
            if g.name in project_gate_names:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Gate '{g.name}' in Suite collides with a Project Quality Gate",
                )

        if suite.contracts or suite.quality_gates or any(sc.contract is not None for sc in suite.scenarios):
            enforce_governed_contract_define(
                principal=current_user,
                project_name=project,
                target_resource=f"/projects/{project}/suites/{suite.name}",
                storage=storage,
                approved_by=x_approved_by,
                external_review_reference=x_external_review_ref,
                details={"action": "suite_create_with_contracts_or_gates"},
            )

        try:
            return storage.create_suite(project, suite)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.get("/{suite}", response_model=Suite)
    def get_suite(project: str, suite: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        res = storage.get_suite(project, suite)
        if not res:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Suite '{suite}' not found")
        return res

    # --- Scenarios ---

    @router.get("/{suite}/scenarios/{scenario}", response_model=Scenario)
    def get_scenario(
        project: str,
        suite: str,
        scenario: str,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "read", storage)
        res = storage.get_scenario(project, suite, scenario)
        if not res:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{scenario}' not found")
        return res

    @router.post("/{suite}/scenarios", response_model=Scenario, status_code=status.HTTP_201_CREATED)
    def create_scenario(
        project: str,
        suite: str,
        scenario: Scenario,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "scenario_create", storage)

        if scenario.contract is not None:
            enforce_governed_contract_define(
                principal=current_user,
                project_name=project,
                target_resource=f"/projects/{project}/suites/{suite}/scenarios/{scenario.name}",
                storage=storage,
                approved_by=x_approved_by,
                external_review_reference=x_external_review_ref,
                details={"action": "scenario_create_with_contract"},
            )

        try:
            return storage.create_scenario(project, suite, scenario)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.put("/{suite}/scenarios/{scenario}", response_model=Scenario)
    def update_scenario(
        project: str,
        suite: str,
        scenario: str,
        updated: Scenario,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "scenario_edit", storage)
        if updated.name != scenario:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scenario name in body must match path")

        current = storage.get_scenario(project, suite, scenario)
        if updated.contract is not None or (current is not None and current.contract is not None):
            enforce_governed_contract_define(
                principal=current_user,
                project_name=project,
                target_resource=f"/projects/{project}/suites/{suite}/scenarios/{scenario}",
                storage=storage,
                approved_by=x_approved_by,
                external_review_reference=x_external_review_ref,
                details={"action": "scenario_put_with_contract"},
            )

        try:
            return storage.update_scenario(project, suite, updated)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    @router.delete("/{suite}/scenarios/{scenario}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_scenario(
        project: str,
        suite: str,
        scenario: str,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "scenario_delete", storage)
        try:
            storage.delete_scenario(project, suite, scenario)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return router
