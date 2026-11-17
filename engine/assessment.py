"""Volume V/VI: assessment of immutable Evidence, without Result resolution."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid

from pydantic import Field, StrictInt, StrictStr
from typing import Literal

from engine.models.base import AQEFBaseModel
from engine.plugins import assessment_reply, invoke
from engine.validators import COST_ORDER, BUILTINS, boundary_attempts, canonical, number, select_target, check_builtin, custom_check


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class JudgeReply(AQEFBaseModel):
    verdict: Literal["pass", "fail"]
    confidence: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    explanation: StrictStr
    assertions: StrictInt = Field(ge=1)


def judge_identity(clause):
    if clause["judge"].get("plugin"):
        return clause["judge"]["plugin"]
    configuration = {key: value for key, value in clause["judge"].items() if key != "plugin"}
    return canonical({"type": "judge", "version": "http-judge-v1", **configuration, "criteria": clause["criteria"]})


def validator_identity(record, clause):
    if clause["validator"].startswith("plugin:"):
        return clause["validator"].removeprefix("plugin:")
    return canonical({"type":"validator", "name":clause["validator"], "version":"1", "target":clause["target"],
                      "expected":clause["expected"], "custom":record["configuration"]["validators"].get(clause["validator"])})


def clause_reference(contract, kind, index):
    clause = contract[kind][index]
    if clause.get("id"):
        return clause["id"]
    digest = hashlib.sha256(canonical(contract).encode("utf-8")).hexdigest()
    return f"sha256:{digest}/{kind}/{index}"


def result_base(record, reference, oracle_type, oracle, evidence):
    return {"id": str(uuid.uuid4()), "execution": record["id"], "clause": reference,
            "oracle_type": oracle_type, "oracle": oracle, "verdict": None,
            "confidence": "not_applicable", "disposition": "oracle_unavailable",
            "supporting_evidence": evidence, "recorded_at": timestamp()}


class AssessmentEngine:
    def __init__(self, storage, provider):
        self.storage = storage
        self.provider = provider

    async def plugin_result(self, record, clause, reference, kind, oracle, resolves, persist):
        from engine.execution import duration

        content_key = "expected" if kind == "validator" else "criteria"
        supporting = {"configuration": deepcopy(clause)}
        result = result_base(record, reference, kind, oracle, supporting)
        try:
            target = clause.get("target")
            evidence = select_target(record, target) if target else {
                "conversation": deepcopy(record["conversation"]), "artifacts": deepcopy(record["artifacts"]),
            }
            raw = await invoke(self.storage, oracle, kind, {
                "evidence": evidence, content_key: clause[content_key],
                "execution": record["id"], "clause": reference,
            }, duration(record["configuration"]["execution"]["timeout"]))
            if kind == "judge" and isinstance(raw, dict) and raw.get("verdict") in ("pass", "fail"):
                supporting["provider_response"] = {"verdict": raw["verdict"]}
            reply = assessment_reply(raw, execution=record["id"], clause=reference, oracle=oracle,
                                     kind=kind, criteria=clause.get("criteria"))
            supporting.update(reply.pop("supporting_evidence"))
            result.update(reply)
            result["disposition"] = ("inconclusive" if kind == "judge"
                                     and result["confidence"] < clause["confidence_threshold"] else "actionable")
        except Exception as exc:
            supporting["error"] = f"Plugin invocation failed ({type(exc).__name__})"
        if resolves:
            result["resolves"] = resolves
        return self.storage.append_result(record["project"], result) if persist else result

    async def assess_validator(self, record, clause, reference, resolves=None, persist=True):
        if clause["validator"].startswith("plugin:"):
            return await self.plugin_result(record, clause, reference, "validator",
                                            validator_identity(record, clause), resolves, persist)
        return self.validate(record, clause, reference, resolves, persist)

    def validate(self, record, clause, reference, resolves=None, persist=True):
        name = clause["validator"]
        custom = record["configuration"]["validators"].get(name)
        oracle = validator_identity(record, clause)
        supporting = {"configuration": deepcopy(clause)}
        result = result_base(record, reference, "validator", oracle, supporting)
        try:
            if name == "boundary" and clause["target"] not in ("artifacts.boundary_attempts", "artifacts.*"):
                raise ValueError("Boundary target must be artifacts.boundary_attempts or artifacts.*")
            target = (deepcopy(boundary_attempts(record["artifacts"])) if name == "boundary"
                      else select_target(record, clause["target"]))
            supporting["target_evidence"] = target
            if name == "tool-call":
                tool_config = record["configuration"]["environment"].get("tool_configuration") or {}
                tools = {tool["name"]: tool["parameters"] for tool in tool_config.get("tools", [])}
                passed, details = check_builtin(name, target, clause["expected"], tools=tools)
            elif name in BUILTINS:
                passed, details = check_builtin(name, target, clause["expected"])
            elif custom is not None:
                if clause["expected"] is not None and clause["expected"] != {}:
                    raise ValueError("Custom Validator expected must be null or {}; the registered rule defines its expectation")
                # The registered pure function receives only target and its frozen rule.
                passed, details = custom_check(target, deepcopy(custom["rule"]))
            else:
                raise ValueError(f"Custom Validator '{name}' is not registered or version is ambiguous")
            supporting["check"] = details
            result["verdict"] = "pass" if passed else "fail"
            result["disposition"] = "actionable"
        except Exception as exc:
            supporting["error"] = f"{type(exc).__name__}: {exc}"
        if resolves:
            result["resolves"] = resolves
        return self.storage.append_result(record["project"], result) if persist else result

    async def judge(self, record, clause, reference, resolves=None, persist=True):
        from engine.execution import duration
        if clause["judge"].get("plugin"):
            return await self.plugin_result(record, clause, reference, "judge",
                                            judge_identity(clause), resolves, persist)
        evidence = {"conversation": deepcopy(record["conversation"]), "artifacts": deepcopy(record["artifacts"])}
        supporting = {"evidence": evidence, "criteria": clause["criteria"], "attempts": []}
        result = result_base(record, reference, "judge", judge_identity(clause), supporting)
        attempt = {"number": 1, "started_at": timestamp()}
        supporting["attempts"].append(attempt)
        try:
            config = clause["judge"]
            if config["model"] not in self.provider.urls:
                raise ValueError(f"No provider URL configured for Judge model '{config['model']}'")
            payload = {"model": config["model"], "criteria": clause["criteria"],
                       "confidence_source": config["confidence_source"], "evidence": deepcopy(evidence)}
            timeout = duration(record["configuration"]["execution"]["timeout"])
            raw = await asyncio.wait_for(self.provider.call(config["model"], payload, timeout), timeout)
            # Diagnostic response is retained even if a verdict has no valid Confidence.
            supporting["provider_response"] = deepcopy(raw)
            reply = JudgeReply.model_validate(raw)
            number(reply.confidence)
            result["verdict"] = reply.verdict
            result["confidence"] = reply.confidence
            result["disposition"] = "actionable" if reply.confidence >= clause["confidence_threshold"] else "inconclusive"
            if reply.assertions > 1:
                result["assertions"] = reply.assertions
            supporting["explanation"] = reply.explanation
        except Exception as exc:
            attempt["error"] = f"{type(exc).__name__}: {str(exc) or 'Judge timeout'}"
        attempt["completed_at"] = timestamp()
        if resolves:
            result["resolves"] = resolves
        return self.storage.append_result(record["project"], result) if persist else result

    async def assess(self, record):
        contract = record["configuration"]["contract"]
        if record["status"] != "completed":
            if boundary_attempts(record["artifacts"]):
                for index, clause in enumerate(contract["constraints"]):
                    if clause["validator"] == "boundary":
                        self.validate(record, clause, clause_reference(contract, "constraints", index))
            return
        constraints = list(enumerate(contract["constraints"]))
        constraints.sort(key=lambda item: COST_ORDER.get(item[1]["validator"], 4))
        outcomes = []
        for index, clause in constraints:
            from engine.scoped import blocked_result
            reference = clause_reference(contract, "constraints", index)
            result = blocked_result(self.storage, record, clause, reference, "validator", validator_identity(record,clause))
            if result is None:
                result = await self.assess_validator(record, clause, reference)
            outcomes.append((clause, result))
        if any(r["disposition"] != "actionable" or (c["veto"] and r["verdict"] == "fail") for c, r in outcomes):
            return
        policy = (contract.get("policies") or {}).get("validator_composition", "AND")
        passes = [r["verdict"] == "pass" for _, r in outcomes]
        passed = not passes or (any(passes) if policy == "OR" else all(passes))
        if not passed:
            return
        for index, clause in enumerate(contract["expectations"]):
            from engine.scoped import assess_expectation
            await assess_expectation(self, record, clause, clause_reference(contract, "expectations", index))
