"""Volume V: pure checks over frozen evidence; no executable custom plugins."""
from copy import deepcopy
import json
import math
import re

from jsonschema import validators, FormatChecker
from referencing import Registry
from pydantic import Field, StrictStr

from engine.models.base import AQEFBaseModel


BUILTINS = {"schema", "structural", "forbidden-content", "latency", "cost", "tool-call", "boundary"}
COST_ORDER = {"latency": 0, "cost": 0, "forbidden-content": 1, "schema": 2, "structural": 3}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return value


def reject_json_constant(value):
    raise ValueError(f"Invalid JSON constant {value}")


def schema_check(target, expected):
    if expected != "json" and not isinstance(expected, (dict, bool)):
        raise ValueError("Schema expected must be a JSON Schema object/boolean or 'json'")

    def local_only(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("$ref", "$dynamicRef", "$recursiveRef") and (not isinstance(child, str) or not child.startswith("#")):
                    raise ValueError("Only local fragment schema references are supported")
                local_only(child)
        elif isinstance(value, list):
            for child in value:
                local_only(child)
    if expected != "json":
        local_only(expected)
        cls = validators.validator_for(expected)
        cls.check_schema(expected)
    if expected == "json" and isinstance(target, str):
        try:
            target = json.loads(target, parse_constant=reject_json_constant)
        except ValueError:
            return False, {"reason": "Target is not valid JSON"}
    if expected == "json":
        return True, {"reason": "Valid JSON"}
    errors = list(cls(expected, format_checker=FormatChecker(), registry=Registry()).iter_errors(target))
    return not errors, {"errors": [{"path": list(e.path), "message": e.message} for e in errors]}


def pattern_check(target, expected):
    if not isinstance(target, str):
        target = canonical(target)
    if not isinstance(expected, dict) or set(expected) != {"patterns"} or not isinstance(expected["patterns"], list):
        raise ValueError("Forbidden-content expected must be {patterns: [...]} ")
    matches = []
    for pattern in expected["patterns"]:
        if isinstance(pattern, str):
            found = pattern in target
        elif isinstance(pattern, dict) and set(pattern) == {"regex"} and isinstance(pattern["regex"], str):
            found = re.search(pattern["regex"], target) is not None
        else:
            raise ValueError("Pattern must be a literal string or {regex: string}")
        if found:
            matches.append(pattern)
    return not matches, {"matched_patterns": matches}


def structural_check(target, expected):
    steps = expected.get("required_steps") if isinstance(expected, dict) and set(expected) == {"required_steps"} else expected
    if not isinstance(steps, list) or not all(isinstance(s, str) and s for s in steps):
        raise ValueError("Structural expected must be a required_steps string list")
    if isinstance(target, dict) and "turns" in target:
        sequence = [t["prompt"] + "\n" + t["response"] for t in target["turns"]]
    elif isinstance(target, list):
        sequence = [v if isinstance(v, str) else canonical(v) for v in target]
    elif isinstance(target, str):
        sequence = [target]
    else:
        raise ValueError("Structural target must be text, a sequence, or Conversation")
    text = "\n".join(sequence)
    position = 0
    matched = []
    for step in steps:
        index = text.find(step, position)
        if index < 0:
            return False, {"matched_steps": matched, "missing_or_out_of_order": step}
        position = index + len(step)
        matched.append(step)
    return True, {"matched_steps": matched}


def select_target(record, path):
    root = {"response": record["conversation"]["turns"][-1]["response"],
            "conversation": record["conversation"], "artifacts": record["artifacts"],
            "duration_ms": record["duration_ms"]}
    if path.startswith("artifacts.") and path != "artifacts.*":
        name, *tail = path[len("artifacts."):].split(".")
        values = [a["data"] for a in record["artifacts"] if a["name"] == name]
        if not values:
            raise ValueError(f"Missing evidence target '{path}'")
        value = values[0] if len(values) == 1 else values
        parts = tail
    elif path == "artifacts.*":
        return deepcopy(record["artifacts"])
    else:
        parts = path.split(".")
        value = root
    for part in parts:
        if isinstance(value, str):
            value = json.loads(value, parse_constant=reject_json_constant)
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value[part]
    return deepcopy(value)


def check_builtin(name, target, expected):
    if name == "schema":
        return schema_check(target, expected)
    if name == "forbidden-content":
        return pattern_check(target, expected)
    if name == "structural":
        return structural_check(target, expected)
    if name == "latency":
        # Local import avoids a module cycle; the parser is a pure duration function.
        from engine.execution import duration
        maximum = duration(expected) * 1000 if isinstance(expected, str) else number(expected)
        if target == []:
            raise ValueError("Missing recorded latency")
        observed = sum(number(v) for v in target) if isinstance(target, list) else number(target)
        return observed <= maximum, {"observed": observed, "maximum_ms": maximum}
    if name == "cost":
        metric = "total_tokens"
        if isinstance(expected, dict) and set(expected) == {"metric", "max"}:
            metric, maximum = expected["metric"], number(expected["max"])
        else:
            maximum = number(expected)
        values = target if isinstance(target, list) else [target]
        if not values:
            raise ValueError("Missing recorded cost/usage")
        observed = sum(number(v[metric] if isinstance(v, dict) else v) for v in values)
        return observed <= maximum, {"observed": observed, "maximum": maximum, "metric": metric}
    raise ValueError(f"Unsupported Validator '{name}' (acting tools are outside engine scope)")


def custom_check(target, rule):
    operation = rule["operation"]
    if operation == "equals":
        passed = canonical(target) == canonical(rule["expected"])
        return passed, {"expected": rule["expected"], "observed": target}
    if operation == "range":
        observed = number(target)
        return rule["minimum"] <= observed <= rule["maximum"], {"observed": observed, "range": rule}
    return check_builtin(operation, target, rule["expected"])


class CustomValidator(AQEFBaseModel):
    name: StrictStr = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    version: StrictStr = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    rule: dict

    def validate_rule(self):
        if self.name in BUILTINS:
            raise ValueError("Custom Validator cannot shadow a built-in")
        operation = self.rule.get("operation")
        if operation not in ("equals", "range", "schema", "forbidden-content", "structural"):
            raise ValueError("Unsupported deterministic Custom Validator operation")
        keys = {"operation", "minimum", "maximum"} if operation == "range" else {"operation", "expected"}
        if set(self.rule) != keys:
            raise ValueError("Unexpected or missing Custom Validator rule fields")
        if operation == "range":
            if number(self.rule["minimum"]) > number(self.rule["maximum"]):
                raise ValueError("Range minimum exceeds maximum")
        else:
            # Validate rule configuration even when a dummy target does not match.
            target = {} if operation == "schema" else ""
            custom_check(target, self.rule)
        canonical(self.rule)
