"""Volume XVI transport and validation for pinned plugin invocations."""

import asyncio
from datetime import datetime

from engine.providers import HTTPProvider
from engine.validators import number


def validate_bindings(storage, configuration):
    from engine.validation import ConfigurationValidationError

    def check(reference, kind, label):
        try:
            active_plugin(storage, reference, kind)
        except ValueError as exc:
            raise ConfigurationValidationError(f"{label}: {exc}") from exc

    def walk(value, label):
        if isinstance(value, list):
            for item in value:
                walk(item, label)
        elif isinstance(value, dict):
            label = value.get("id") or value.get("name") or label
            validator = value.get("validator")
            if isinstance(validator, str) and validator.startswith("plugin:"):
                check(validator.removeprefix("plugin:"), "validator", f"Clause '{label}'")
            if "plugin" in value:
                kind = "dataset" if value.get("source") == "plugin" else "judge"
                check(value["plugin"], kind, f"{'Dataset' if kind == 'dataset' else 'Clause'} '{label}'")
            for key in ("datasets", "suites", "scenarios", "contracts", "contract", "constraints",
                        "expectations", "judge", "judges", "multi_judge", "seeded_control", "confirmation"):
                walk(value.get(key), label)

    walk(configuration.model_dump(mode="json"), "unnamed")


def active_plugin(storage, reference, kind):
    plugin = storage.decision_record("plugin", "__global__", reference)
    if (not plugin or plugin["type"] != kind
            or storage.decision_record("plugin_deprecation", "__global__", reference)
            or plugin["endpoint"] not in storage.plugin_urls):
        raise ValueError(f"Plugin '{reference}' must be an active, allowlisted {kind} version")
    return plugin


async def invoke(storage, reference, kind, content, timeout):
    plugin = active_plugin(storage, reference, kind)
    endpoint = plugin["endpoint"]
    async with asyncio.timeout(timeout):
        return await HTTPProvider({reference: endpoint}).call(
            reference, content | {"configuration": plugin["configuration"]}, timeout, strict_json=True,
        )


def assessment_reply(raw, *, execution, clause, oracle, kind, criteria=None):
    required = {"id", "execution", "clause", "oracle_type", "oracle", "verdict", "confidence",
                "disposition", "supporting_evidence", "recorded_at"}
    if not isinstance(raw, dict) or not required <= raw.keys():
        raise ValueError("Incomplete plugin Result")
    if (raw["execution"] != execution or raw["clause"] != clause or raw["oracle"] != oracle
            or raw["oracle_type"] != kind or raw["verdict"] not in ("pass", "fail")
            or not isinstance(raw["id"], str) or not raw["id"]
            or not isinstance(raw["recorded_at"], str)):
        raise ValueError("Invalid plugin Result identity or verdict")
    if datetime.fromisoformat(raw["recorded_at"]).tzinfo is None:
        raise ValueError("Plugin Result timestamp requires a timezone")
    confidence = raw["confidence"]
    evidence = raw["supporting_evidence"]
    if kind == "validator":
        if confidence != "not_applicable" or raw["disposition"] != "actionable":
            raise ValueError("Invalid Validator Plugin confidence or disposition")
    elif (not 0 <= number(confidence) <= 1 or raw["disposition"] not in ("actionable", "inconclusive")
          or not isinstance(evidence, dict) or evidence.get("criteria") != criteria):
        raise ValueError("Invalid Judge Plugin confidence, criteria or disposition")
    assertions = raw.get("assertions")
    if "assertions" in raw:
        if kind != "judge" or type(assertions) is not int or assertions < 2:
            raise ValueError("Invalid plugin assertions")
        required.add("assertions")
    return {
        "verdict": raw["verdict"], "confidence": confidence,
        "supporting_evidence": {"assessment": evidence, "ignored_reply_fields": sorted(raw.keys() - required)},
        **({"assertions": assertions} if assertions is not None else {}),
    }
