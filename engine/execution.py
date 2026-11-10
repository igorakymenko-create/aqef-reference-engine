"""Volume III: deterministic pipeline and isolated, bounded execution pool."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import time
import uuid

from fastapi import HTTPException
from pydantic import Field

from engine.composition import compose_scenario_effective_contract, effective_contract_data
from engine.auth import check_permission
from engine.dataset_sources import REPLAY_PERMISSION
from engine.models.base import AQEFBaseModel
from engine.models.dataset import DatasetSource
from engine.models.evidence import Conversation, Turn
from engine.providers import SubjectReply, SubjectToolReply
from engine.tool_runtime import ToolRuntime


SUBJECT_STEP_LIMIT = 32


class ExecutionRequest(AQEFBaseModel):
    suite: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    gates: list[str] | None = None


def now():
    return datetime.now(timezone.utc).isoformat()


def duration(value):
    if isinstance(value,str) and value.startswith("P"):
        iso = re.fullmatch(r"P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?",value)
        if iso and any(iso.groups()):
            seconds=sum(float(v or 0)*factor for v,factor in zip(iso.groups(),(86400,3600,60,1)))
            if 0<seconds<float("inf"):return seconds
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
            for key, value in config.model_dump(mode="json", context={"include_absent":True}, exclude_unset=True).items():
                if value is None:
                    raise ValueError(f"Execution setting '{key}' cannot be explicitly null")
                result[key] = value
    duration(result["timeout"])
    if result["scheduling"] not in ("sequential", "parallel"):
        raise ValueError("Unsupported scheduling strategy: " + result["scheduling"])
    return result


class ExecutionEngine:
    def __init__(self, storage, provider, executor):
        self.storage = storage
        self.provider = provider
        self.executor = executor

    def prepare(self, project_name, request, principal):
        store = self.storage
        project = store.get_project(project_name)
        suite = store.get_suite(project_name, request.suite)
        env = store.get_environment(project_name, request.environment)
        if project is None or suite is None or env is None:
            raise HTTPException(404, "Project, Suite or Environment not found")
        gate_definitions = project.quality_gates + suite.quality_gates
        applicable={g.name for g in gate_definitions}
        if request.gates and not set(request.gates)<=applicable:
            raise HTTPException(422,"Requested Gates must apply to this Suite/Environment scope")
        batch = str(uuid.uuid4())
        records = []
        covered_dimensions = set()
        try:
            config = settings(project, suite)
            for scenario in suite.scenarios:
                effective = compose_scenario_effective_contract(
                    project.contracts, suite.contracts, scenario.contract,
                    lambda name: store.get_contract(project_name, name))
                if scenario.seeded_control is None:
                    covered_dimensions.update(clause.dimension.value for clause in [*effective.constraints, *effective.expectations])
                if effective.policies and effective.policies.validator_composition not in ("AND", "OR", "hard-veto"):
                    raise ValueError("Unsupported validator_composition")
                for expectation in effective.expectations:
                    if expectation.judge and expectation.judge.confidence_source.value == "agreement":
                        raise ValueError("Single Judge cannot use panel agreement as its Confidence")
                    judges = [expectation.judge] if expectation.judge else (expectation.multi_judge.judges or [expectation.multi_judge.judge]) if expectation.multi_judge else []
                    for judge in judges:
                        if judge.model.strip().lower() == env.model_version.strip().lower():
                            raise ValueError("Independent Oracle violation: Judge and subject models must differ")
                    if expectation.multi_judge and expectation.multi_judge.consensus.method not in ("voting","confidence_weighted_mean"):
                        raise ValueError("Unsupported Consensus method")
                    if expectation.review_timeout:duration(expectation.review_timeout)
                if scenario.seeded_control:
                    control=scenario.seeded_control
                    defect=next((c for c in project.defect_classes if c.name==control.defect_class),None)
                    refs=control.reference_oracles or (defect.reference_oracles if defect else None) or []
                    tested=[j.model for e in effective.expectations for j in ([e.judge] if e.judge else (e.multi_judge.judges or [e.multi_judge.judge]) if e.multi_judge else [])]
                    if any(ref.model.strip().lower()==model.strip().lower() for ref in refs for model in tested):
                        raise ValueError(f"Control '{scenario.name}' reference Oracle is not independent of tested Oracle")
                definitions = store.list_custom_validators(project_name)
                frozen_validators = {}
                to_freeze=list(effective.constraints)
                if scenario.seeded_control and scenario.seeded_control.confirmation:to_freeze.append(scenario.seeded_control.confirmation)
                for constraint in to_freeze:
                    matching = [d for d in definitions if constraint.validator in (d["name"], d["name"] + "@" + d["version"])]
                    if len(matching) == 1:
                        frozen_validators[constraint.validator] = matching[0]
                rows = [(None, scenario.variables or {}, None)]
                if scenario.dataset:
                    name, version = scenario.dataset.split("@", 1)
                    dataset = store.get_dataset(project_name, name, version)
                    if dataset is None:
                        raise ValueError(f"Dataset '{scenario.dataset}' not found")
                    if dataset.source == DatasetSource.PRODUCTION_REPLAY:
                        check_permission(principal, REPLAY_PERMISSION, store)
                        rows = [
                            (row.id, {}, [turn.prompt for turn in Conversation.model_validate(
                                row.variables["conversation"]).turns])
                            for row in dataset.rows
                        ]
                    else:
                        rows = [(row.id, row.variables, None) for row in dataset.rows]
                if scenario.evidence:
                    Conversation.model_validate(scenario.evidence.conversation)
                elif env.model_version not in self.provider.urls:
                    raise ValueError(f"No provider URL configured for model '{env.model_version}'")
                for row_id, variables, replay_prompts in rows:
                    prompt = None
                    if replay_prompts is not None:
                        prompt = replay_prompts[0]
                    elif not scenario.evidence:
                        prompt = render(scenario.prompt.template, variables)
                    record = {
                        "id": str(uuid.uuid4()), "execution_batch_id": batch,
                        "project": project_name, "suite": suite.name, "scenario": scenario.name,
                        "principal_id": principal.id, "principal_kind": principal.kind.value,
                        "environment": env.name, "dataset": scenario.dataset, "row_id": row_id,
                        "variables": deepcopy(variables), "configuration": {
                            "environment": env.model_dump(mode="json", context={"include_absent":True}),
                            "scenario": scenario.model_dump(mode="json", context={"include_absent":True}),
                            "contract": effective_contract_data(effective),
                            "validators": deepcopy(frozen_validators),
                            "defect_classes":[c.model_dump(mode="json", context={"include_absent":True}) for c in project.defect_classes],
                            "execution": deepcopy(config)},
                        "scheduling": {"strategy": config["scheduling"], "order": len(records),
                                       "reason": "on_demand Suite × Environment; declaration order",
                                       "requested_by": principal.id, "requested_at": now()},
                        "status": "queued", "created_at": now(), "started_at": None,
                        "completed_at": None, "attempts": [], "retry_count": 0,
                        "conversation": None, "partial_turns": [], "artifacts": [],
                        "error": None, "opening_prompt": prompt,
                    }
                    if replay_prompts is not None:
                        record["replay_prompts"] = replay_prompts
                    records.append(record)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        # All batch inputs are validated before recording or invoking any subject.
        warnings = [{"gate":gate.name, "reason":f"Suite '{suite.name}' has no non-Seeded-Control clause in dimension '{gate.aggregate}'"}
                    for gate in gate_definitions if gate.on_failure == "block_release"
                    and gate.aggregate in {"functional", "semantic", "operational", "safety"}
                    and gate.aggregate not in covered_dimensions]
        store.save_executions(records, {"id":batch, "project":project_name, "suite":suite.name,
                                       "environment":env.name, "created_at":now(), "warnings":warnings})
        return batch, records, warnings

    async def execute(self, record):
        config = record["configuration"]["execution"]
        env = record["configuration"]["environment"]
        fixed = record["configuration"]["scenario"]["evidence"]
        replay_prompts = record.get("replay_prompts")
        record["status"] = "running"
        record["started_at"] = now()
        self.storage.update_execution(record)
        started = time.monotonic()
        deadline = started + duration(config["timeout"])
        retries = config["retry"]["max_attempts"] if config["retry"] else 0
        received = False
        turns = []
        replay_index = 0
        tools = ToolRuntime(self.storage, self.executor, record)
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
                        acting = env["tool_configuration"] is not None
                        if acting and len(turns) >= SUBJECT_STEP_LIMIT:
                            raise RuntimeError("Subject step limit exceeded")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Execution deadline exceeded")
                        if turns and "tool_calls" in turns[-1]:
                            prompt = "Continue."
                        elif replay_prompts is not None:
                            prompt = replay_prompts[replay_index]
                        else:
                            prompt = record["opening_prompt"] if not turns else "Continue."
                        payload = {"model": env["model_version"], "prompt": prompt,
                                   "environment": deepcopy(env), "variables": deepcopy(record["variables"]),
                                   "context": {"turns": deepcopy(turns)}}
                        call_start = time.monotonic()
                        try:
                            options = {"strict_json": True} if acting else {}
                            raw = await asyncio.wait_for(
                                self.provider.call(env["model_version"], payload, remaining, **options), remaining,
                            )
                        finally:
                            record["artifacts"].append({"name": "latency_ms",
                                "data": (time.monotonic() - call_start) * 1000,
                                "turn": len(turns) + 1, "attempt": attempt["number"]})
                        tool_turn = isinstance(raw, dict) and "tool_calls" in raw
                        # Never replay a subject turn that requested a tool.
                        if tool_turn:
                            received = True
                        elif isinstance(raw, dict) and isinstance(raw.get("response"), str):
                            received = True
                            turns.append({"prompt": prompt, "response": raw["response"]})
                        if time.monotonic() >= deadline and not tool_turn:
                            raise TimeoutError("Execution deadline exceeded")
                        if tool_turn:
                            if not acting:
                                raise ValueError("Tool calls require an Environment with tool_configuration")
                            json.dumps(raw, allow_nan=False, ensure_ascii=False).encode("utf-8")
                            reply = SubjectToolReply.model_validate(raw)
                            calls = [call.model_dump(exclude_none=True) for call in reply.tool_calls]
                            turns.append({"prompt": prompt, "tool_calls": calls})
                            if time.monotonic() >= deadline:
                                for call in calls:
                                    tools.refuse_after_failure(call, turns)
                                raise TimeoutError("Execution deadline exceeded")
                        else:
                            reply = SubjectReply.model_validate(raw)
                        for name, data in reply.artifacts.items():
                            if (env.get("action_boundary") or {}).get("enforced") and name in (
                                "boundary_attempt", "boundary_attempts",
                            ):
                                continue  # Boundary observations are owned by the harness.
                            if acting and name in ("tool_call", "tool_calls", "tool_result"):
                                continue
                            record["artifacts"].append({"name": name, "data": deepcopy(data), "turn": len(turns)})
                        if reply.usage:
                            record["artifacts"].append({"name": "usage", "data": reply.usage, "turn": len(turns)})
                        if tool_turn:
                            await tools.handle(calls, turns, deadline)
                            continue
                        replay_index += 1
                        complete = (replay_index == len(replay_prompts)
                                    if replay_prompts is not None else reply.complete)
                        if complete:
                            record["conversation"] = {"turns": turns}
                            record["partial_turns"] = []
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
        batch, records, warnings = self.prepare(project, request, principal)
        if records:
            config = records[0]["configuration"]["execution"]
            pool = asyncio.Semaphore(config["parallelization"] if config["scheduling"] == "parallel" else 1)

            async def worker(record):
                async with pool:
                    await self.execute(record)
                    from engine.assessment import AssessmentEngine
                    await AssessmentEngine(self.storage, self.provider).assess(record)
            from engine.scoped import ControlManager
            manager=ControlManager(self.storage)
            groups={}
            for record in records:
                if record["configuration"]["scenario"]["seeded_control"] is not None:
                    groups.setdefault(record["scenario"],[]).append(record)
            for group in groups.values():
                if manager.halted(project,batch):break
                for record in group:await worker(record)
                manager.record(group)
            ordinary=[r for r in records if r["configuration"]["scenario"]["seeded_control"] is None]
            if not manager.halted(project,batch):await asyncio.gather(*(worker(record) for record in ordinary))
            for record in records:
                if record["status"]=="queued":
                    record.update(status="cancelled",error="halt_run",completed_at=now())
                    self.storage.update_execution(record)
            manager.ensure_unrun(records)
        from engine.scoped import decorate_execution
        records=[decorate_execution(self.storage,r) for r in records]
        response={"execution_batch_id":batch,"executions":records,"warnings":warnings}
        if request.gates:
            from engine.decision import DecisionEngine
            with self.storage.config_lock:response["gate_evaluation"]=DecisionEngine(self.storage).evaluate(project,batch)
        return response
