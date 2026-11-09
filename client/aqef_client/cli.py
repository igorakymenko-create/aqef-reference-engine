"""Command-line presentation of the AQEF REST API."""

import argparse
import json
import math
import os
from pathlib import Path
import sys

import yaml

from . import APIError, Client, TransportError, __version__
from ._commands import COMMANDS


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_abbrev=False, **kwargs)

    def error(self, message):
        self.print_usage(sys.stderr)
        token = os.environ.get("AQEF_TOKEN")
        if token:
            message = message.replace(token, "<redacted>")
        if message.startswith("unrecognized arguments:"):
            message = "unrecognized arguments; see --help"
        self.exit(64, f"{self.prog}: {message}\n")


def connection_options(parser):
    parser.add_argument("--url", default=argparse.SUPPRESS, help="engine URL (or AQEF_URL)")
    parser.add_argument("--token-file", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS, metavar="SECONDS")
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS)


def build_parser():
    parser = Parser(prog="aqef", description="AQEF reference REST client")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    connection_options(parser)
    groups = parser.add_subparsers(dest="resource", required=True)
    actions = {}
    for spec in sorted(COMMANDS):
        command, method, verb, path, path_args, query, headers, has_body = spec
        resource, action = command.split()
        if resource not in actions:
            actions[resource] = groups.add_parser(resource).add_subparsers(
                dest="action", required=True,
            )
        leaf = actions[resource].add_parser(action, help=f"{verb} {path}")
        connection_options(leaf)
        leaf.set_defaults(operation=spec)
        for name in path_args:
            leaf.add_argument("--" + name.replace("_", "-"), required=True)
        for _, name in query + headers:
            leaf.add_argument("--" + name.replace("_", "-"))
        if method == "trigger_execution":
            leaf.add_argument("file", type=Path, nargs="?")
            leaf.add_argument("--suite")
            leaf.add_argument("--environment")
            leaf.add_argument("--wait", action="store_true",
                              help="wait for the engine's synchronous response")
        elif has_body:
            leaf.add_argument("file", type=Path)
    return parser


def read_body(file):
    text = file.read_text(encoding="utf-8-sig")
    return json.loads(text) if file.suffix.lower() == ".json" else yaml.safe_load(text)


def arguments(args, parser):
    _, method, _, _, path, query, headers, has_body = args.operation
    kwargs = {key: getattr(args, key) for key in path}
    kwargs.update({name: getattr(args, name) for _, name in query + headers})
    if method == "trigger_execution":
        if args.file is None:
            if args.suite is None or args.environment is None:
                parser.error("execution run requires FILE or both --suite and --environment")
            return kwargs | {"body": {"suite": args.suite, "environment": args.environment}}
        if args.suite is not None or args.environment is not None:
            parser.error("choose FILE or --suite and --environment")
    if has_body:
        try:
            kwargs["body"] = read_body(args.file)
            # Confirm serializability without changing the parsed request.
            json.dumps(kwargs["body"], allow_nan=False)
        except (OSError, ValueError, TypeError, yaml.YAMLError, RecursionError):
            parser.error("FILE must be readable YAML or JSON with a JSON-serializable body")
    return kwargs


GATE_RESPONSES = {
    "check_gates", "generate_report", "get_report", "list_reports",
    "record_release", "get_release", "list_releases",
}


def gate_results(operation, data):
    if operation == "trigger_execution" and isinstance(data, dict):
        data = data.get("gate_evaluation")
    elif operation not in GATE_RESPONSES:
        return
    for record in data if isinstance(data, list) else [data]:
        if isinstance(record, dict) and isinstance(record.get("gates"), dict):
            yield from ((name, result) for name, result in record["gates"].items()
                        if isinstance(result, dict))


def write(stream, content, secret):
    if secret:
        content = content.replace(secret, b"<redacted>")
    stream.buffer.write(content)
    stream.buffer.flush()


def render(response, operation, raw, secret):
    try:
        data = response.json()
    except ValueError:
        data = None
        formatted = response.content
    else:
        formatted = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    gates = list(gate_results(operation, data))
    if raw:
        write(sys.stdout, response.content, secret)
    else:
        for name, result in gates:
            if result.get("override"):
                write(sys.stdout, f"Gate {name}: overridden\n".encode(), secret)
        if operation == "override_gate" and isinstance(data, dict) and data.get("approval_id"):
            write(sys.stdout, b"GateResult overridden\n", secret)
        write(sys.stdout, formatted, secret)
    return int(any(gate.get("blocking") is True and gate.get("status") == "fail"
                   and not gate.get("override") for _, gate in gates))


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    url = getattr(args, "url", os.environ.get("AQEF_URL"))
    if not url:
        parser.error("set AQEF_URL or pass --url")
    try:
        token = (args.token_file.read_text(encoding="utf-8-sig").strip()
                 if hasattr(args, "token_file") else os.environ.get("AQEF_TOKEN"))
    except (OSError, UnicodeError):
        parser.error("could not read the token file")
    if not token:
        parser.error("set AQEF_TOKEN or pass --token-file")
    if not token.isascii() or any(c.isspace() or not c.isprintable() for c in token):
        parser.error("the bearer token must be printable ASCII without spaces")
    timeout = getattr(args, "timeout", 60.0)
    if not math.isfinite(timeout) or timeout <= 0:
        parser.error("--timeout must be positive and finite")
    kwargs = arguments(args, parser)
    secret = token.encode()
    method = args.operation[1]
    try:
        with Client(url, token, timeout=timeout) as client:
            response = getattr(client, method)(**kwargs)
    except APIError as error:
        write(sys.stderr, f"HTTP {error.status_code}\n".encode() + error.body, secret)
        return 2
    except (TransportError, ValueError):
        print("AQEF transport error or timeout", file=sys.stderr)
        return 3
    return render(response, method, getattr(args, "json", False), secret)


if __name__ == "__main__":
    raise SystemExit(main())
