"""Materialize immutable Dataset versions at registration (Volume IV, A.8)."""

import asyncio
from datetime import datetime, timezone
import json

from fastapi import HTTPException
import httpx
from pydantic import Field, StrictBool, TypeAdapter

from engine.models.base import AQEFBaseModel
from engine.models.dataset import Dataset, DatasetSource, Row
from engine.models.evidence import Conversation


SOURCE_TIMEOUT = 30.0
REPLAY_PERMISSION = "production_replay_read"
ROW_LIST = TypeAdapter(list[Row])


class CapturedConversation(AQEFBaseModel):
    id: str = Field(min_length=1)
    conversation: Conversation
    anonymized: StrictBool


class CaptureReply(AQEFBaseModel):
    conversations: list[CapturedConversation]


def record_generator_independence(dataset, environments):
    if dataset.source == DatasetSource.GENERATED and any(
        dataset.generator.model.strip().casefold() == env.model_version.strip().casefold()
        for env in environments
    ):
        return dataset.model_copy(update={"independence": "same_identifier_as_subject"})
    return dataset


def set_dataset_warnings(response, datasets):
    warnings = [
        {"dataset": dataset.name, "version": dataset.version, "code": dataset.independence,
         "message": "The generator identifier matches a subject identifier"}
        for dataset in datasets if dataset.independence
    ]
    if warnings:
        response.headers["X-AQEF-Warnings"] = json.dumps(warnings)


async def read_source(provider, identifier, payload, purpose):
    if identifier not in provider.urls:
        raise HTTPException(422, f"No configured {purpose} source for the requested identifier")
    try:
        return await asyncio.wait_for(
            provider.call(identifier, payload, SOURCE_TIMEOUT, strict_json=True),
            timeout=SOURCE_TIMEOUT,
        )
    except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
        # Source response content may contain private production data.
        raise HTTPException(502, f"Dataset {purpose} source failed or returned invalid JSON") from None


async def materialize(definition, generator_provider, capture_provider, raw_sources):
    data = definition.model_dump(mode="json")
    if definition.source == DatasetSource.STATIC:
        return Dataset.model_validate(data)

    if definition.source == DatasetSource.GENERATED:
        payload = data["generator"]
        reply = await read_source(generator_provider, payload["model"], payload, "generation")
        rows = reply["rows"] if isinstance(reply, dict) and set(reply) == {"rows"} else reply
        try:
            ROW_LIST.validate_python(rows)
            data["rows"] = rows
            data["generated_at"] = datetime.now(timezone.utc)
            # Reject overflowed floats in arbitrary JSON variable values.
            json.dumps(rows, allow_nan=False, ensure_ascii=False).encode("utf-8")
            return Dataset.model_validate(data)
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(502, "Dataset generation returned invalid or duplicate Rows") from None

    config = definition.capture
    if not config.anonymization and config.source not in raw_sources:
        raise HTTPException(422, "Capture policy requires anonymization for this source")
    reply = await read_source(capture_provider, config.source, data["capture"], "capture")
    try:
        captures = CaptureReply.model_validate(reply).conversations
        if len(captures) != config.sample_size:
            raise ValueError("Capture count must match sample_size")
        if any(item.anonymized != config.anonymization for item in captures):
            raise ValueError("Capture anonymization must match the requested policy")
        data["rows"] = [
            {"id": item.id, "variables": {"conversation": item.conversation.model_dump(mode="json")}}
            for item in captures
        ]
        data["captured_at"] = datetime.now(timezone.utc)
        return Dataset.model_validate(data)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(502, "Dataset capture returned invalid Conversations or unverified anonymization") from None
