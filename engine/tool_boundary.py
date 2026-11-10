"""Pure target matching and tool argument validation for the Action Boundary."""

import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry


IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]+")
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HOST = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")


def url_target(value):
    """Return a conservative canonical origin and literal path."""
    if any(ord(char) < 33 or ord(char) > 126 or char in "\\%?#*" for char in value):
        raise ValueError("Unsupported characters in boundary URL")
    parsed = urlsplit(value)
    host = parsed.hostname
    if (parsed.scheme not in ("http", "https") or not host or not HOST.fullmatch(host)
            or parsed.username is not None or parsed.netloc.endswith(":")):
        raise ValueError("Boundary URLs need an HTTP(S) origin with a plain host")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port if parsed.port is not None else default_port
    path = parsed.path or "/"
    if port == 0 or any(segment in (".", "..") for segment in path.split("/")):
        raise ValueError("Unsupported port or path in boundary URL")
    return (parsed.scheme, host, port), path


def validate_pattern(pattern):
    if IDENTIFIER.fullmatch(pattern):
        return
    if pattern.endswith("/*"):
        url_target(pattern[:-1])
    else:
        url_target(pattern)


def matches(pattern, target):
    if IDENTIFIER.fullmatch(pattern):
        return pattern == target
    try:
        wildcard = pattern.endswith("/*")
        origin, path = url_target(pattern[:-1] if wildcard else pattern)
        other_origin, other_path = url_target(target)
    except ValueError:
        return False
    return origin == other_origin and (
        other_path.startswith(path) if wildcard else path == other_path
    )


def destination_values(value, *, url_key=False):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from destination_values(item, url_key=key.casefold() == "url")
    elif isinstance(value, list):
        for item in value:
            yield from destination_values(item, url_key=url_key)
    elif isinstance(value, str) and (url_key or URL_SCHEME.match(value.strip()) or value.strip().startswith("//")):
        yield value


def validate_parameter_schema(schema):
    Draft202012Validator.check_schema(schema)
    if isinstance(schema, dict) and schema.get("$schema", "https://json-schema.org/draft/2020-12/schema").rstrip("#") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("Tool parameters require draft 2020-12 schemas")

    def check_refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("$ref", "$dynamicRef") and (
                    not isinstance(child, str) or not child.startswith("#")
                ):
                    raise ValueError("Tool parameter schemas only support local fragment references")
                check_refs(child)
        elif isinstance(value, list):
            for child in value:
                check_refs(child)
    check_refs(schema)


def argument_errors(arguments, parameters):
    """Each declared parameter is required and has an independent TypeDef."""
    errors = []
    for name in sorted(set(parameters) - set(arguments)):
        errors.append({"argument": name, "reason": "missing"})
    for name in sorted(set(arguments) - set(parameters)):
        errors.append({"argument": name, "reason": "unexpected"})
    for name in sorted(set(parameters) & set(arguments)):
        try:
            validator = Draft202012Validator(
                parameters[name], registry=Registry(), format_checker=FormatChecker(),
            )
            for error in validator.iter_errors(arguments[name]):
                errors.append({"argument": name, "reason": error.validator,
                               "path": list(error.path)})
        except Exception:
            # An unresolved schema must never turn into permission to dispatch.
            errors.append({"argument": name, "reason": "invalid parameter schema"})
    return errors


def decide_boundary(tool, arguments, boundary, *, declared):
    destinations = list(dict.fromkeys(destination_values(arguments)))
    entries = boundary["entries"] if boundary else []
    tool_entries = [entry for entry in entries if matches(entry["target"], tool)]
    targets = list(destinations) if destinations else [tool]
    if destinations and tool_entries:
        targets = [tool, *destinations]
    if not declared and tool not in targets:
        targets.insert(0, tool)
    targets = list(dict.fromkeys(targets))

    denied = []
    tripwires = []
    kinds = set()
    for target in targets:
        candidates = [
            entry for entry in entries
            if (target not in destinations or not IDENTIFIER.fullmatch(entry["target"]))
            and matches(entry["target"], target)
        ]
        if not candidates or (target == tool and not declared):
            denied.append(target)
            continue
        # Restrictive matches win, independent of declaration order.
        if any(entry["kind"] == "stub" for entry in candidates):
            kinds.add("stub")
        elif any(entry["kind"] == "sandbox" for entry in candidates):
            kinds.add("sandbox")
        else:
            kinds.add("real")
        if any(entry["tripwire"] for entry in candidates):
            tripwires.append(target)

    if denied:
        return None, targets, denied, tripwires
    if "stub" in kinds:
        return "stub", targets, [], tripwires
    if len(kinds) != 1:
        return None, targets, targets, tripwires
    return kinds.pop(), targets, [], tripwires
