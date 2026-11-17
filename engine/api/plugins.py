"""Versioned external plugin registry (Volume XVI, Appendix C §C.3)."""

import asyncio
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, StrictStr

from engine.auth import check_permission
from engine.decision import now
from engine.models.base import AQEFBaseModel
from engine.plugins import assessment_reply
from engine.providers import HTTPProvider
from engine.validators import canonical


Component = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]


class PluginRegistration(AQEFBaseModel):
    type: Literal["validator", "judge", "dataset", "report"]
    name: Component
    version: Component
    endpoint: StrictStr
    configuration: dict


def get_plugins_router(storage, principal_dep, urls):
    router = APIRouter(prefix="/plugins", tags=["Plugins"])
    registry = "__global__"
    provider = HTTPProvider({url: url for url in urls.values()})

    def get(plugin):
        record = storage.decision_record("plugin", registry, plugin)
        if record is None:
            raise HTTPException(404, "Plugin version not found")
        return record

    def with_status(record):
        retired = storage.decision_record("plugin_deprecation", registry, record["id"])
        return record | {"deprecated_at": retired["deprecated_at"] if retired else None}

    @router.get("")
    def list_plugins(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                     principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        records = storage.decision_records("plugin", registry)
        return [with_status(record) for record in records[offset:offset + limit]]

    @router.post("", status_code=201)
    async def register_plugin(request: PluginRegistration, principal=Depends(principal_dep)):
        check_permission(principal, "plugin_register", storage)
        if request.endpoint not in provider.urls:
            raise HTTPException(422, "Plugin endpoint is not on the operator allowlist")
        plugin = f"{request.name}@{request.version}"
        if storage.decision_record("plugin", registry, plugin) is not None:
            raise HTTPException(409, "Plugin version already exists and is immutable")
        record = request.model_dump(mode="json") | {"id": plugin, "registered_at": now()}
        if request.type == "validator":
            await check_validator_repetition(provider, request, plugin)
            record["repeatability_check"] = {"runs": 2, "output_matched": True}
        return with_status(storage.save_decision("plugin", registry, record))

    @router.get("/{plugin}")
    def get_plugin(plugin: str, principal=Depends(principal_dep)):
        check_permission(principal, "read", storage)
        record = get(plugin)
        versions = [with_status(item) for item in storage.decision_records("plugin", registry)
                    if item["name"] == record["name"]]
        return with_status(record) | {"versions": versions}

    @router.post("/{plugin}/deprecate")
    def deprecate_plugin(plugin: str, principal=Depends(principal_dep)):
        check_permission(principal, "plugin_admin", storage)
        record = get(plugin)
        storage.save_decision("plugin_deprecation", registry, {"id": plugin, "deprecated_at": now()})
        return with_status(record)

    return router


async def check_validator_repetition(provider, request, plugin):
    payload = {
        "evidence": {"turns": []},
        "expected": None,
        "configuration": request.configuration,
        "execution": "repeatability-probe",
        "clause": "repeatability-probe",
    }
    replies = []
    try:
        for _ in range(2):
            async with asyncio.timeout(5):
                reply = await provider.call(request.endpoint, payload, 5, strict_json=True)
            assessment_reply(reply, execution=payload["execution"], clause=payload["clause"],
                             oracle=plugin, kind="validator")
            replies.append(canonical(reply))
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise HTTPException(422, "Validator Plugin repeatability probe did not return a valid Result") from exc
    if replies[0] != replies[1]:
        raise HTTPException(422, "Validator Plugin output varied on the fixed repeatability probe")
