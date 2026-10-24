"""Volume V/VI: assessment of immutable Evidence, without Result resolution."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid

from pydantic import Field, StrictInt, StrictStr
from typing import Literal

from engine.models.base import AQEFBaseModel
from engine.validators import COST_ORDER, BUILTINS, canonical, number, select_target, check_builtin, custom_check


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class JudgeReply(AQEFBaseModel):
    verdict: Literal["pass", "fail"]
    confidence: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    explanation: StrictStr
    assertions: StrictInt = Field(ge=1)


def judge_identity(clause):
    return canonical({"type": "judge", "version": "http-judge-v1", **clause["judge"], "criteria": clause["criteria"]})


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

    def validate(self, record, clause, reference):
        name = clause["validator"]
        custom = record["configuration"]["validators"].get(name)
        oracle = canonical({"type": "validator", "name": name, "version": "1",
                            "target": clause["target"], "expected": clause["expected"], "custom": custom})
        supporting = {"configuration": deepcopy(clause)}
        result = result_base(record, reference, "validator", oracle, supporting)
        try:
            target = select_target(record, clause["target"])
            supporting["target_evidence"] = target
            if name in BUILTINS:
                passed, details = check_builtin(name, target, clause["expected"])
            elif custom is not None:
                if clause["expected"] is not None:
                    raise ValueError("Custom Validator expected must be null; the registered rule defines its expectation")
                # The registered pure function receives only target and its frozen rule.
                passed, details = custom_check(target, deepcopy(custom["rule"]))
            else:
                raise ValueError(f"Custom Validator '{name}' is not registered or version is ambiguous")
            supporting["check"] = details
            result["verdict"] = "pass" if passed else "fail"
            result["disposition"] = "actionable"
        except Exception as exc:
            supporting["error"] = f"{type(exc).__name__}: {exc}"
        return self.storage.append_result(record["project"], result)

    async def judge(self, record, clause, reference):
        from engine.execution import duration
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
        return self.storage.append_result(record["project"], result)

    async def assess(self, record):
        if record["status"] != "completed":
            return
        contract = record["configuration"]["contract"]
        constraints = list(enumerate(contract["constraints"]))
        constraints.sort(key=lambda item: COST_ORDER.get(item[1]["validator"], 4))
        outcomes = []
        for index, clause in constraints:
            result = self.validate(record, clause, clause_reference(contract, "constraints", index))
            outcomes.append((clause, result))
        if any(r["disposition"] != "actionable" or (c["veto"] and r["verdict"] == "fail") for c, r in outcomes):
            return
        policy = (contract.get("policies") or {}).get("validator_composition", "AND")
        passes = [r["verdict"] == "pass" for _, r in outcomes]
        passed = not passes or (any(passes) if policy == "OR" else all(passes))
        if not passed:
            return
        for index, clause in enumerate(contract["expectations"]):
            await self.judge(record, clause, clause_reference(contract, "expectations", index))
