"""Environment API endpoints.

References:
- Volume II — Domain Model (§Environment)
- Appendix A §A.2
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.8
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from engine.auth import check_permission
from engine.models.environment import Environment
from engine.models.principal import Principal
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_environments_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/environments", tags=["Environments"])

    @router.get("", response_model=List[Environment])
    def list_environments(project: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_environments(project)

    @router.post("", response_model=Environment, status_code=status.HTTP_201_CREATED)
    def create_environment(
        project: str,
        environment: Environment,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "environment_create", storage)
        try:
            return storage.create_environment(project, environment)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.get("/{env}", response_model=Environment)
    def get_environment(
        project: str,
        env: str,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "read", storage)
        res = storage.get_environment(project, env)
        if not res:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Environment '{env}' not found")
        return res

    @router.put("/{env}", response_model=Environment)
    def update_environment(
        project: str,
        env: str,
        environment: Environment,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "environment_edit", storage)
        if environment.name != env:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Environment name in body must match path")
        try:
            return storage.update_environment(project, environment)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    @router.delete("/{env}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_environment(
        project: str,
        env: str,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "environment_delete", storage)
        try:
            storage.delete_environment(project, env)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return router
