"""Datasets API endpoints.

References:
- Volume IV — Dataset Engine (§Static, §Versioning)
- Appendix A §A.8
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.6
"""

from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from engine.auth import check_permission
from engine.dataset_sources import REPLAY_PERMISSION, check_generator_independence, materialize
from engine.models.dataset import Dataset, DatasetInput, DatasetSource, Row
from engine.models.principal import AuditLogEntry, Principal
from engine.storage import Storage, StorageConflictError, StorageNotFoundError


def get_datasets_router(storage: Storage, get_principal_dep, provider, capture_provider, raw_sources) -> APIRouter:
    router = APIRouter(prefix="/projects/{project}/datasets", tags=["Datasets"])

    async def register(project: str, definition: DatasetInput, principal: Principal) -> Dataset:
        check_permission(principal, "dataset_create", storage)
        if definition.source == DatasetSource.PRODUCTION_REPLAY:
            check_permission(principal, REPLAY_PERMISSION, storage)
        if definition.source != DatasetSource.STATIC:
            current = storage.get_project(project)
            if current is None:
                raise HTTPException(404, f"Project '{project}' not found")
            if storage.get_dataset(project, definition.name, definition.version) is not None:
                raise HTTPException(409, f"Dataset '{definition.name}@{definition.version}' is immutable")
            check_generator_independence(definition, current.environments)

        dataset = await materialize(definition, provider, capture_provider, raw_sources)
        try:
            with storage.config_lock:
                current = storage.get_project(project)
                if current is not None:
                    check_generator_independence(dataset, current.environments)
                if storage.replay_protected(project):
                    check_permission(principal, REPLAY_PERMISSION, storage)
                storage.create_dataset(project, dataset)
        except StorageNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        storage.create_audit_entry(AuditLogEntry(
            id=str(uuid4()), project=project, action="dataset_create",
            principal_id=principal.id, principal_kind=principal.kind,
            details={"dataset": dataset.name, "version": dataset.version, "source": dataset.source.value},
        ))
        return dataset

    @router.get("", response_model=List[Dataset])
    def list_datasets(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        return storage.list_datasets(project)[offset:offset + limit]

    @router.post("", response_model=Dataset, status_code=status.HTTP_201_CREATED)
    async def create_dataset(
        project: str,
        dataset: DatasetInput,
        current_user: Principal = Depends(get_principal_dep),
    ):
        return await register(project, dataset, current_user)

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
    async def create_dataset_version(
        project: str,
        dataset: str,
        new_version: DatasetInput,
        current_user: Principal = Depends(get_principal_dep),
    ):
        check_permission(current_user, "dataset_create", storage)
        if new_version.name != dataset:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dataset name in body must match path")
        return await register(project, new_version, current_user)

    return router
