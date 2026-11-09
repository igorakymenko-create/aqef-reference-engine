"""Project API endpoints.

References:
- Volume II — Domain Model (§Project)
- Appendix A §A.1
- Appendix B §B.2, §B.3
- Appendix C §C.3, §C.5, §C.8
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from engine.auth import check_permission, enforce_governed_contract_define, get_principal_permissions, governed_values
from engine.dataset_sources import (
    REPLAY_PERMISSION, materialize, record_generator_independence, set_dataset_warnings,
)
from engine.models.dataset import DatasetSource
from engine.models.principal import Principal
from engine.models.project import Project, ProjectInput
from engine.storage import Storage, StorageConflictError, StorageNotFoundError
from engine.validation import ConfigurationValidationError, validate_project_configuration
from engine.audit import bind_project, record_dataset_creation


def has_governed_definitions(project):
    return bool(governed_values(project))



def declaration_fields(dataset):
    fields = dataset.model_dump(
        mode="json", exclude={"rows", "generated_at", "captured_at", "independence"},
    )
    if not fields.get("mechanisms"):
        fields.pop("mechanisms", None)
    return fields


def get_projects_router(
    storage: Storage, get_principal_dep, provider, capture_provider, raw_sources,
) -> APIRouter:
    router = APIRouter(prefix="/projects", tags=["Projects"])

    def check_project_write(config, actor, create, approved_by, review_ref, *, record):
        name = config.name
        if storage.replay_protected(name):
            check_permission(actor, REPLAY_PERMISSION, storage, record=record)
        current = storage.get_project(name)
        if create and current is not None:
            raise HTTPException(409, f"Project '{name}' already exists")
        if not create and current is None:
            raise HTTPException(404, f"Project '{name}' not found")
        validate_project_configuration(
            config,
            lookup_reusable_contract=lambda key: storage.get_contract(name, key),
            lookup_dataset=lambda key, version: storage.get_dataset(name, key, version),
        )
        governed = has_governed_definitions(config) if create else governed_values(config) != governed_values(current)
        if governed:
            enforce_governed_contract_define(
                principal=actor, project_name=name, target_resource=f"/projects/{name}",
                storage=storage, approved_by=approved_by, external_review_reference=review_ref,
                details={"action": "project_create_with_contracts_or_gates" if create
                         else "project_put_with_contracts_or_gates"}, record=record,
            )

    def lookup_version(name, definition, actor, *, record):
        if definition.source == DatasetSource.STATIC:
            return None
        if definition.source == DatasetSource.PRODUCTION_REPLAY:
            check_permission(actor, REPLAY_PERMISSION, storage, record=record)
        existing = storage.get_dataset(name, definition.name, definition.version)
        if existing is not None:
            if declaration_fields(existing) != declaration_fields(definition):
                raise StorageConflictError(f"Dataset '{definition.name}@{definition.version}' is immutable")
        else:
            check_permission(actor, "dataset_create", storage, record=record)
        return existing

    async def load_project(config, actor, response, approved_by, review_ref, *, create):
        name = config.name
        bind_project(name)
        try:
            with storage.config_lock:
                check_project_write(config, actor, create, approved_by, review_ref, record=False)
                pending = [
                    definition for definition in config.datasets
                    if lookup_version(name, definition, actor, record=False) is None
                ]

            # Provider calls stage data in memory. No database transaction or
            # configuration lock is held across an await.
            staged = {
                (definition.name, definition.version): await materialize(
                    definition, provider, capture_provider, raw_sources,
                )
                for definition in pending
            }

            with storage.config_lock:
                resolved = []
                created = []
                for definition in config.datasets:
                    key = (definition.name, definition.version)
                    existing = lookup_version(name, definition, actor, record=True)
                    if existing is not None:
                        resolved.append(existing)
                        continue
                    dataset = staged.get(key)
                    if dataset is None:
                        raise StorageConflictError(f"Dataset '{key[0]}@{key[1]}' changed during load")
                    dataset = record_generator_independence(dataset, config.environments)
                    resolved.append(dataset)
                    if dataset.source != DatasetSource.STATIC:
                        created.append(dataset)

                candidate = Project.model_validate(
                    config.model_dump(mode="json", exclude={"datasets"}) | {"datasets": resolved},
                )
                check_project_write(candidate, actor, create, approved_by, review_ref, record=True)
                # Storage writes all configuration and Dataset rows in one transaction.
                saved = storage.create_project(candidate) if create else storage.update_project(candidate)
            for dataset in created:
                record_dataset_creation(storage, name, dataset, actor)
            set_dataset_warnings(response, created)
            return saved
        except StorageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except StorageNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ConfigurationValidationError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("", response_model=List[Project])
    def list_projects(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        projects = storage.list_projects()
        if REPLAY_PERMISSION not in get_principal_permissions(current_user, storage):
            projects = [project for project in projects if not storage.replay_protected(project.name)]
        return projects[offset:offset + limit]

    @router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
    async def create_project(
        project: ProjectInput,
        response: Response,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "project_create", storage)
        return await load_project(
            project, current_user, response, x_approved_by, x_external_review_ref, create=True,
        )

    @router.get("/{project}", response_model=Project)
    def get_project(project: str, current_user: Principal = Depends(get_principal_dep)):
        check_permission(current_user, "read", storage)
        proj = storage.get_project(project)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project '{project}' not found")
        return proj

    @router.put("/{project}", response_model=Project)
    async def update_project(
        project: str,
        updated: ProjectInput,
        response: Response,
        current_user: Principal = Depends(get_principal_dep),
        x_approved_by: Optional[str] = Header(None, alias="X-Approved-By"),
        x_external_review_ref: Optional[str] = Header(None, alias="X-External-Review-Ref"),
    ):
        check_permission(current_user, "project_edit", storage)
        if updated.name != project:
            raise HTTPException(400, "Project name in body must match path")
        return await load_project(
            updated, current_user, response, x_approved_by, x_external_review_ref, create=False,
        )

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
