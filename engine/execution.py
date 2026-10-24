"""Volume III: deterministic pipeline and isolated, bounded execution pool."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import time
import uuid

from fastapi import HTTPException
from pydantic import Field, StrictStr

from engine.composition import compose_scenario_effective_contract
from engine.models.base import AQEFBaseModel
from engine.providers import SubjectReply


class Turn(AQEFBaseModel):
    prompt: StrictStr
    response: StrictStr


class Conversation(AQEFBaseModel):
    turns: list[Turn] = Field(min_length=1)


class ExecutionRequest(AQEFBaseModel):
    suite: str = Field(min_length=1)
    environment: str = Field(min_length=1)


def now():
    return datetime.now(timezone.utc).isoformat()


def duration(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value or "")
    if not match:
        raise ValueError("timeout must be a positive duration with unit ms, s, m, or h")
    seconds = float(match[1]) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[match[2]]
    if not 0 < seconds < float("inf"):
        raise ValueError("timeout must be finite and positive")
    return seconds


def render(template, variables):
    def replace(match):
        name = match[1]
        if name not in variables:
            raise ValueError(f"Missing prompt variable '{name}'")
        value = variables[name]
        return value if isinstance(value, str) else json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, template)


def settings(project, suite):
    result = {"timeout": "30s", "scheduling": "sequential", "parallelization": 1, "retry": None}
    for config in (project.execution, suite.execution):
        if config:
            for key, value in config.model_dump(mode="json", exclude_unset=True).items():
                if value is None:
                    raise ValueError(f"Execution setting '{key}' cannot be explicitly null")
                result[key] = value
    duration(result["timeout"])
    if result["scheduling"] not in ("sequential", "parallel"):
        raise ValueError("Unsupported scheduling strategy: " + result["scheduling"])
    return result


class ExecutionEngine:
    def __init__(self, storage, provider):
        self.storage = storage
        self.provider = provider

    def prepare(self, project_name, request, principal):
        store = self.storage
        project = store.get_project(project_name)
        suite = store.get_suite(project_name, request.suite)
        env = store.get_environment(project_name, request.environment)
        if project is None or suite is None or env is None:
            raise HTTPException(404, "Project, Suite or Environment not found")
        batch = str(uuid.uuid4())
        records = []
        try:
            config = settings(project, suite)
            for scenario in suite.scenarios:
                effective = compose_scenario_effective_contract(
                    project.contracts, suite.contracts, scenario.contract,
                    lambda name: store.get_contract(project_name, name))
                if effective.policies and effective.policies.validator_composition not in ("AND", "OR", "hard-veto"):
                    raise ValueError("Unsupported validator_composition")
                for expectation in effective.expectations:
                    if expectation.judge is None:
                        raise ValueError("Human Review and Multi Judge execution are deferred to slice 5")
                    if expectation.judge.confidence_source.value == "agreement":
                        raise ValueError("Single Judge cannot use panel agreement as its Confidence")
                    if expectation.judge.model.strip().lower() == env.model_version.strip().lower():
                        raise ValueError("Independent Oracle violation: Judge and subject models must differ")
                definitions = store.list_custom_validators(project_name)
                frozen_validators = {}
                for constraint in effective.constraints:
                    matching = [d for d in definitions if constraint.validator in (d["name"], d["name"] + "@" + d["version"])]
                    if len(matching) == 1:
                        frozen_validators[constraint.validator] = matching[0]
                rows = [(None, scenario.variables or {})]
                if scenario.dataset:
                    name, version = scenario.dataset.split("@", 1)
                    dataset = store.get_dataset(project_name, name, version)
                    if dataset is None:
                        raise ValueError(f"Dataset '{scenario.dataset}' not found")
                    rows = [(row.id, row.variables) for row in dataset.rows]
                if scenario.evidence:
                    Conversation.model_validate(scenario.evidence.conversation)
                elif env.model_version not in self.provider.urls:
                    raise ValueError(f"No provider URL configured for model '{env.model_version}'")
                for row_id, variables in rows:
                    prompt = None if scenario.evidence else render(scenario.prompt.template, variables)
                    records.append({
                        "id": str(uuid.uuid4()), "execution_batch_id": batch,
                        "project": project_name, "suite": suite.name, "scenario": scenario.name,
                        "environment": env.name, "dataset": scenario.dataset, "row_id": row_id,
                        "variables": deepcopy(variables), "configuration": {
                            "environment": env.model_dump(mode="json"),
                            "scenario": scenario.model_dump(mode="json"),
                            "contract": effective.model_dump(mode="json"),
                            "validators": deepcopy(frozen_validators),
                            "execution": deepcopy(config)},
                        "scheduling": {"strategy": config["scheduling"], "order": len(records),
                                       "reason": "on_demand Suite × Environment; declaration order",
                                       "requested_by": principal.id, "requested_at": now()},
                        "status": "queued", "created_at": now(), "started_at": None,
                        "completed_at": None, "attempts": [], "retry_count": 0,
                        "conversation": None, "partial_turns": [], "artifacts": [],
                        "error": None, "opening_prompt": prompt,
                    })
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        # All batch inputs are validated before recording or invoking any subject.
        store.save_executions(records)
        return batch, records

    async def execute(self, record):
        config = record["configuration"]["execution"]
        env = record["configuration"]["environment"]
        fixed = record["configuration"]["scenario"]["evidence"]
        record["status"] = "running"
        record["started_at"] = now()
        self.storage.update_execution(record)
        started = time.monotonic()
        deadline = started + duration(config["timeout"])
        retries = config["retry"]["max_attempts"] if config["retry"] else 0
        received = False
        turns = []
        if fixed:
            record["conversation"] = deepcopy(fixed["conversation"])
            record["artifacts"] = [{"name": key, "data": deepcopy(value), "turn": None}
                                   for key, value in (fixed["artifacts"] or {}).items()]
            record["source_execution"] = fixed["source_execution"]
            record["status"] = "completed"
        else:
            while True:
                attempt = {"number": len(record["attempts"]) + 1, "started_at": now(), "error": None}
                record["attempts"].append(attempt)
                try:
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Execution deadline exceeded")
                        prompt = record["opening_prompt"] if not turns else "Continue."
                        payload = {"model": env["model_version"], "prompt": prompt,
                                   "environment": deepcopy(env), "variables": deepcopy(record["variables"]),
                                   "context": {"turns": deepcopy(turns)}}
                        call_start = time.monotonic()
                        try:
                            raw = await asyncio.wait_for(self.provider.call(env["model_version"], payload, remaining), remaining)
                        finally:
                            record["artifacts"].append({"name": "latency_ms",
                                "data": (time.monotonic() - call_start) * 1000,
                                "turn": len(turns) + 1, "attempt": attempt["number"]})
                        # Recognize genuine text before validating the envelope, preventing do-overs.
                        if isinstance(raw, dict) and isinstance(raw.get("response"), str):
                            received = True
                            turns.append({"prompt": prompt, "response": raw["response"]})
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Execution deadline exceeded")
                        reply = SubjectReply.model_validate(raw)
                        for name, data in reply.artifacts.items():
                            record["artifacts"].append({"name": name, "data": deepcopy(data), "turn": len(turns)})
                        if reply.usage:
                            record["artifacts"].append({"name": "usage", "data": reply.usage, "turn": len(turns)})
                        if reply.complete:
                            record["conversation"] = {"turns": turns}
                            record["status"] = "completed"
                            break
                    attempt["completed_at"] = now()
                    break
                except Exception as exc:
                    attempt["error"] = f"{type(exc).__name__}: {str(exc) or 'Execution deadline exceeded'}"
                    attempt["completed_at"] = now()
                    if received or len(record["attempts"]) > retries or time.monotonic() >= deadline:
                        record["error"] = attempt["error"]
                        record["status"] = "infrastructure_failure"
                        record["partial_turns"] = turns
                        break
                    record["retry_count"] += 1
        record["duration_ms"] = (time.monotonic() - started) * 1000
        record["completed_at"] = now()
        self.storage.update_execution(record)

    async def run(self, project, request, principal):
        batch, records = self.prepare(project, request, principal)
        if records:
            config = records[0]["configuration"]["execution"]
            pool = asyncio.Semaphore(config["parallelization"] if config["scheduling"] == "parallel" else 1)

            async def worker(record):
                async with pool:
                    await self.execute(record)
                    from engine.assessment import AssessmentEngine
                    await AssessmentEngine(self.storage, self.provider).assess(record)
            await asyncio.gather(*(worker(record) for record in records))
        return {"execution_batch_id": batch, "executions": records}
