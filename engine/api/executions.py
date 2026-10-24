"""Appendix C execution and immutable assessment resources."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from engine.auth import check_permission
from engine.execution import ExecutionEngine, ExecutionRequest


def get_executions_router(storage, principal_dep, provider):
    router = APIRouter(prefix="/projects/{project}/executions", tags=["Executions"])
    engine = ExecutionEngine(storage, provider)

    def get_record(project, execution):
        record = storage.get_execution(project, execution)
        if record is None:
            raise HTTPException(404, "Execution not found")
        return record

    @router.post("", status_code=201)
    async def trigger(project: str, request: ExecutionRequest, principal=Depends(principal_dep)):
        check_permission(principal, "execute", storage)
        return await engine.run(project, request, principal)

    @router.get("")
    def list_records(project: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                     suite: str | None = None, environment: str | None = None, status: str | None = None,
                     date_from: datetime | None = None, date_to: datetime | None = None,
                     principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        if (date_from and date_from.tzinfo is None) or (date_to and date_to.tzinfo is None):
            raise HTTPException(422, "Date filters must include a timezone")
        rows = storage.list_executions(project)
        if not rows and storage.get_project(project) is None:
            raise HTTPException(404, "Project not found")
        rows = [r for r in rows if (suite is None or r["suite"] == suite)
                and (environment is None or r["environment"] == environment)
                and (status is None or r["status"] == status)
                and (date_from is None or datetime.fromisoformat(r["created_at"]) >= date_from)
                and (date_to is None or datetime.fromisoformat(r["created_at"]) <= date_to)]
        return rows[offset:offset + limit]

    @router.get("/{execution}")
    def metadata(project: str, execution: str, principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        return get_record(project, execution)

    @router.get("/{execution}/conversation")
    def conversation(project: str, execution: str, principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        record = get_record(project, execution)
        if record["conversation"] is None:
            raise HTTPException(409, "Execution has no completed Conversation")
        return record["conversation"]

    @router.get("/{execution}/artifacts")
    def artifacts(project: str, execution: str, offset: int = Query(0, ge=0),
                  limit: int = Query(100, ge=1, le=1000), principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        return get_record(project, execution)["artifacts"][offset:offset + limit]

    @router.get("/{execution}/results")
    def results(project: str, execution: str, offset: int = Query(0, ge=0),
                limit: int = Query(100, ge=1, le=1000), oracle_type: str | None = None,
                verdict: str | None = None, principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        get_record(project, execution)
        rows = storage.list_results(project, execution)
        return [r for r in rows if (oracle_type is None or r["oracle_type"] == oracle_type)
                and (verdict is None or r["verdict"] == verdict)][offset:offset + limit]

    return router
