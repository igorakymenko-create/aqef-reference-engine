"""Datasets API endpoints.

References:
- Volume IV — Dataset Engine (§Static, §Versioning)
- Appendix A §A.8
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.6
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from engine.auth import check_permission
from engine.models.dataset import Dataset, Row
from engine.models.principal import Principal
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_datasets_router(storage: Storage, get_principal_dep) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/datasets", tags=["Datasets"])

    @router.get("", response_model=List[Dataset])
    def list_datasets(project: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_datasets(project)

    @router.post("", response_model=Dataset, status_code=status.HTTP_201_CREATED)
    def create_dataset(
        project: str,
        dataset: Dataset,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "dataset_create", storage)
        try:
            return storage.create_dataset(project, dataset)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    @router.get("/{dataset}", response_model=Dataset)
    def get_dataset(
        project: str,
        dataset: str,
        version: Optional[str] = Query(None),
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "read", storage)
        res = storage.get_dataset(project, dataset, version=version)
        if not res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{dataset}' (version={version or 'latest'}) not found",
            )
        return res

    @router.get("/{dataset}/rows", response_model=List[Row])
    def get_dataset_rows(
        project: str,
        dataset: str,
        version: Optional[str] = Query(None),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "read", storage)
        res = storage.get_dataset(project, dataset, version=version)
        if not res or res.rows is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{dataset}' not found",
            )
        return res.rows[offset : offset + limit]

    @router.post("/{dataset}/versions", response_model=Dataset, status_code=status.HTTP_201_CREATED)
    def create_dataset_version(
        project: str,
        dataset: str,
        new_version: Dataset,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "dataset_create", storage)
        if new_version.name != dataset:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dataset name in body must match path")
        try:
            return storage.create_dataset(project, new_version)
        except StorageNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except StorageConflictError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return router
