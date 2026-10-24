"""AQEF Reference Engine — FastAPI Application.

References:
- BRIEF.md §4 (FastAPI, SQLite, Bearer token)
- Appendix C — REST API Specification
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from engine.api.contracts import get_contracts_router
from engine.api.datasets import get_datasets_router
from engine.api.environments import get_environments_router
from engine.api.gates import get_gates_router
from engine.api.governance import get_governance_router
from engine.api.projects import get_projects_router
from engine.api.suites_scenarios import get_suites_scenarios_router
from engine.auth import get_current_principal_dependency
from engine.models.principal import Principal, PrincipalKind, Role, Team
from engine.storage import Storage, StorageConflictError
from engine.providers import HTTPProvider, load_provider_urls
from engine.api.executions import get_executions_router
from engine.api.assessment import get_assessment_router
from engine.api.decision import get_decision_router
from engine.api.scoped import get_scoped_router


def create_app(db_path: str = ":memory:") -> FastAPI:
    provider = HTTPProvider(load_provider_urls())
    storage = Storage(db_path=db_path)

    # Bootstrap default admin team, role, and principal if not already present
    existing_teams = {t.id for t in storage.list_teams()}
    if "admin-team" not in existing_teams:
        admin_team = Team(id="admin-team", name="Administration", description="System Administrators")
        storage.create_team(admin_team)

    if not storage.get_role("admin"):
        admin_role = Role(name="admin", permissions=["admin"])
        storage.create_role(admin_role)

    if not storage.get_principal("admin"):
        admin_token = os.environ.get("AQEF_ADMIN_TOKEN", "admin-token")
        admin_principal = Principal(
            id="admin",
            kind=PrincipalKind.PERSON,
            name="System Administrator",
            email="admin@aqef.local",
            team_ids=["admin-team"],
            roles=["admin"],
        )
        storage.create_principal(admin_principal, token=admin_token)

    principal_dep = get_current_principal_dependency(lambda: storage)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="AQEF Reference Engine",
        version="0.41.1",
        description="Reference Implementation for the AI Quality Engineering Framework (AQEF) specification WD 0.41.1",
        lifespan=lifespan,
    )
    app.state.storage = storage
    app.state.provider = provider

    @app.exception_handler(StorageConflictError)
    async def storage_conflict(request: Request, exc: StorageConflictError):
        return JSONResponse(status_code=409, content={"detail":str(exc)})

    # Register Routers
    app.include_router(get_governance_router(storage, principal_dep))
    app.include_router(get_projects_router(storage, principal_dep))
    app.include_router(get_environments_router(storage, principal_dep))
    app.include_router(get_suites_scenarios_router(storage, principal_dep))
    app.include_router(get_contracts_router(storage, principal_dep))
    app.include_router(get_datasets_router(storage, principal_dep))
    app.include_router(get_gates_router(storage, principal_dep))
    app.include_router(get_executions_router(storage, principal_dep, provider))
    app.include_router(get_assessment_router(storage, principal_dep))
    app.include_router(get_decision_router(storage, principal_dep, provider))
    app.include_router(get_scoped_router(storage, principal_dep))

    @app.get("/healthz", tags=["System"])
    def health_check():
        return {"status": "ok", "specification_version": "0.41.1"}

    return app


app = create_app(db_path=os.environ.get("AQEF_DB_PATH", "aqef.db"))
