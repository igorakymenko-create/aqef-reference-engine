"""Regenerate the SDK operation surface and CLI inventory from engine OpenAPI."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "client" / "aqef_client"
SPEC = json.loads((ROOT / "docs/OPENAPI.json").read_text(encoding="utf-8"))
ALIASES = {
    "trigger": ("trigger_execution", "execution run"),
    "list_records": ("list_executions", "execution list"),
    "metadata": ("get_execution", "execution get"),
    "conversation": ("get_conversation", "execution conversation"),
    "artifacts": ("list_artifacts", "execution artifacts"),
    "results": ("list_results", "result list"),
    "admit": ("record_admission", "admission record"),
    "admissions": ("list_admissions", "admission list"),
    "register": ("register_validator", "validator register"),
    "validators": ("list_validators", "validator list"),
    "evaluate": ("check_gates", "gates check"),
    "snapshot": ("capture_snapshot", "snapshot capture"),
    "report": ("generate_report", "report generate"),
    "override": ("override_gate", "gate override"),
    "baseline": ("approve_baseline", "baseline approve"),
    "policy": ("approve_release_policy", "release-policy approve"),
    "revoke": ("revoke_release_policy", "release-policy revoke"),
    "release": ("record_release", "release record"),
    "review": ("review_result", "result review"),
    "reassess": ("reassess_result", "result reassess"),
    "confirm": ("confirm_seeded_control", "seeded-control confirm"),
    "invalidate": ("invalidate_seeded_control", "seeded-control invalidate"),
    "requalify": ("record_requalification", "requalification record"),
    "requalifications": ("list_requalifications", "requalification list"),
    "list_quality_gates": ("list_quality_gates", "gate list"),
    "create_quality_gate": ("create_quality_gate", "gate create"),
    "update_quality_gate": ("update_quality_gate", "gate update"),
    "list_release_policies": ("list_release_policies", "release-policy list"),
    "create_project": ("create_project", "project load"),
    "get_audit_log": ("get_audit_log", "audit list"),
    "get_approvals": ("list_approvals", "approval list"),
    "health_check": ("health_check", "system health"),
    "create_dataset_version": ("create_dataset_version", "dataset version"),
    "get_dataset_rows": ("get_dataset_rows", "dataset rows"),
}
for plural, singular in {
    "snapshots": "snapshot", "baselines": "baseline", "reports": "report",
    "releases": "release", "release_policies": "release_policy",
}.items():
    ALIASES[f"get_{plural}"] = (
        f"get_{singular}", f"{singular.replace('_', '-')} get",
    )

EXTENSIONS = {
    ("GET", "/projects/{project}/gates/evaluations/{evaluation}"): "Read a specific stored Gate evaluation and its current overrides for Volume XIII.",
    ("POST", "/principals"): "Principal provisioning is implementation-defined in C.4.",
    ("GET", "/projects/{project}/executions"): "Execution history and filters extend C.6.",
    ("GET", "/projects/{project}/validators"): "Local Custom Validator inventory for Volume V.",
    ("POST", "/projects/{project}/validators"): "Local declarative Custom Validator registration for Volume V.",
    ("POST", "/projects/{project}/reports"): "Explicit freeze operation for the C.10 Report shape.",
    ("GET", "/projects/{project}/releases/{key}"): "Direct lookup of an immutable C.3 Release Decision.",
    ("GET", "/healthz"): "Engine health and version metadata.",
}


def option(name):
    return name.lower().replace("-", "_")


def schema_type(schema):
    types = schema.get("anyOf", [schema])
    return " | ".join(
        {"integer": "int", "boolean": "bool", "string": "str", "null": "None"}
        .get(item.get("type"), "object") for item in types
    )


def build():
    source = [
        '"""Generated from docs/OPENAPI.json by client/tools/generate_operations.py."""',
        "",
        "import httpx",
        "",
        "from ._transport import Transport, segment",
        "",
        "",
        "class Operations(Transport):",
        '    """Named operations exposed by the reference API."""',
    ]
    registry = []
    for path, methods in SPEC["paths"].items():
        for verb, op in methods.items():
            verb = verb.upper()
            suffix = re.sub(r"[^a-zA-Z0-9_]", "_", path)
            raw = op["operationId"].removesuffix(f"{suffix}_{verb.lower()}")
            if raw in ALIASES:
                name, command = ALIASES[raw]
            else:
                name = raw
                action, resource = raw.split("_", 1)
                if action == "list":
                    resource = resource.removesuffix("s")
                command = f"{resource.replace('_', '-')} {action}"
            paths, query, headers = [], [], []
            required = []
            optional = []
            for param in op.get("parameters", []):
                key, location = param["name"], param["in"]
                if key.lower() == "authorization":
                    continue
                arg = option(key)
                hint = schema_type(param["schema"])
                if location == "path":
                    paths.append(arg)
                    required.append(f"{arg}: {hint}")
                else:
                    (query if location == "query" else headers).append((key, arg))
                    assert not param.get("required"), param
                    if "None" not in hint.split(" | "):
                        hint += " | None"
                    optional.append(f"{arg}: {hint} = None")
            body = "requestBody" in op
            if body:
                required.append("body: object")
            fields = ["self", *required, *(["*", *optional] if optional else [])]
            source.extend(["", f"    def {name}("])
            source.extend(f"        {item}," for item in fields)
            source.extend([
                "    ) -> httpx.Response:",
                f'        """{verb} {path}."""',
                "        return self.request(",
                f'            "{verb}",',
                "            " + ("f" if paths else "") + '"' +
                re.sub(r"{(\w+)}", r"{segment(\1)}", path) + '",',
            ])
            if body:
                source.append("            body=body,")
            for kind, params in [("params", query), ("headers", headers)]:
                if params:
                    source.append(f"            {kind}={{")
                    for key, arg in params:
                        source.append(f'                "{key}": {arg},')
                    source.append("            },")
            source.append("        )")
            registry.append((command, name, verb, path, paths, query, headers, body))
    assert len({row[0] for row in registry}) == len(registry)
    assert len({row[1] for row in registry}) == len(registry)
    # Optional values are omitted at the HTTP boundary by the shared transport.
    (PACKAGE / "_operations.py").write_text("\n".join(source) + "\n", encoding="utf-8")
    (PACKAGE / "_commands.py").write_text(
        '"""Generated CLI operation inventory. See client/tools/generate_operations.py."""\n\n'
        + "COMMANDS = (\n" + "".join(f"    {row!r},\n" for row in registry) + ")\n",
        encoding="utf-8",
    )
    cli = ROOT / "docs/CLI.md"
    head = cli.read_text(encoding="utf-8").split("<!-- operations -->")[0]
    rows = ["<!-- operations -->", "", "| Command | SDK method | HTTP call | Appendix C |",
            "|---|---|---|---|"]
    for command, name, verb, path, paths, query, headers, body in sorted(registry):
        args = "".join(f" --{p.replace('_', '-')} {p.upper()}" for p in paths)
        args += "".join(f" [--{arg.replace('_', '-')} VALUE]" for _, arg in query + headers)
        if name == "trigger_execution":
            args += " (FILE or --suite S --environment E) [--wait]"
        elif body:
            args += " FILE"
        cite = "Not in Appendix C" if (verb, path) in EXTENSIONS else "C.3"
        if cite == "C.3" and any(key in path for key in ("/review", "/reassess")):
            cite += ", C.7"
        if cite == "C.3" and name in ("generate_report", "get_report", "list_reports"):
            cite += ", C.10"
        if name == "delete_project":
            cite += ", C.8"
        rows.append(f"| `aqef {command}{args}` | `{name}` | `{verb} {path}` | {cite} |")
    rows.extend(["", f"{len(registry)} commands.", "", "## Not in Appendix C", ""])
    for command, name, verb, path, *_ in sorted(registry):
        if (verb, path) in EXTENSIONS:
            rows.append(f"- `aqef {command}` wraps `{verb} {path}`. {EXTENSIONS[verb, path]}")
    cli.write_text(head + "\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
