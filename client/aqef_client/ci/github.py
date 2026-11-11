"""Translate the engine's recorded Gate outcomes into a GitHub step result."""

from html import escape
import math
import os
from pathlib import Path
import time

from aqef_client import APIError, Client, TransportError


def positive_seconds(name, default):
    seconds = float(os.environ.get(name, default))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Expected finite positive seconds")
    return seconds


def outcome_for(gates):
    overridden = False
    for gate in gates.values():
        if type(gate["blocking"]) is not bool or gate["status"] not in ("pass", "fail"):
            raise ValueError("Unknown GateResult shape")
        if gate["blocking"] and gate["status"] == "fail":
            if not gate.get("override"):
                return "fail"
            overridden = True
    return "pass_with_override" if overridden else "pass"


def append(path, content, token):
    if token:
        content = content.replace(token, "[redacted]")
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(content)


def cell(value, token):
    text = str(value)
    if token:
        text = text.replace(token, "[redacted]")
    return (escape(text).replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;")
            .replace("\r", " ").replace("\n", " "))


def main():
    token = os.environ.get("AQEF_TOKEN", "")
    output = os.environ.get("GITHUB_OUTPUT")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    batch, gates, outcome = "", {}, "fail"
    note = ""
    try:
        if not token or not output or not summary:
            raise ValueError("Missing Action environment")
        deadline = time.monotonic() + positive_seconds("AQEF_WAIT_TIMEOUT", "60")
        interval = positive_seconds("AQEF_POLL_INTERVAL", "2")
        url, project = os.environ["AQEF_URL"], os.environ["AQEF_PROJECT"]
        suite, environment = os.environ["AQEF_SUITE"], os.environ["AQEF_ENVIRONMENT"]
        policy = os.environ.get("AQEF_RELEASE_POLICY")

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise TimeoutError()
            return seconds

        def call(method, *args):
            with Client(url, token, timeout=remaining()) as client:
                return getattr(client, method)(project, *args).json()

        batch = os.environ.get("AQEF_BATCH", "")
        if not batch:
            batch = call("trigger_execution", {"suite": suite, "environment": environment})["execution_batch_id"]
        if not isinstance(batch, str) or not batch or "\n" in batch or "\r" in batch:
            batch = ""
            raise ValueError("Invalid batch identifier")
        request = {"execution_batch_id": batch, "suite": suite, "environment": environment,
                   "wait_for_batch": True}
        initial = call("check_gates", request)
        while initial.get("status") == "pending":
            time.sleep(min(interval, remaining()))
            initial = call("check_gates", request)
        evaluation_id, gates = initial["id"], initial["gates"]
        while True:
            view = call("get_gate_evaluation", evaluation_id)
            gates = view["gates"]
            if not view["scope_current"]:
                note = "The stored evaluation's scope changed."
                break
            if view["refresh_required"]:
                fresh = call("check_gates", request | {"previous_evaluation_id": evaluation_id})
                evaluation_id, gates = fresh["id"], fresh["gates"]
                # A refresh may race with another Evidence change.
                continue
            translated = outcome_for(gates)
            if translated != "fail":
                if policy and translated == "pass":
                    report = call("generate_report", {
                        "execution_batch_id": batch, "evaluation_id": evaluation_id,
                    })
                    call("record_release", {
                        "execution_batch_id": batch, "report_id": report["id"],
                        "snapshot_id": report["snapshot_id"], "decision": "approved",
                        "release_policy": policy,
                    })
                    note = "Release Decision recorded."
                elif policy:
                    note = "The standing release policy applies to an unoverridden pass."
                outcome = translated
                break
            time.sleep(min(interval, remaining()))
    except TimeoutError:
        note = "Wait timeout expired."
    except APIError as error:
        note = f"Engine returned HTTP {error.status_code}."
    except TransportError:
        note = "Engine transport failed or the request timed out."
    except (KeyError, TypeError, ValueError, AttributeError):
        note = "Action inputs or engine response were invalid."

    if output:
        append(output, f"execution_batch={batch}\noutcome={outcome}\n", token)
    if summary:
        lines = [f"## AQEF outcome `{outcome}`", "", note, "",
                 "| Gate | Type | Status | Override |", "|---|---|---|---|"]
        if isinstance(gates, dict):
            for name, gate in gates.items():
                if not isinstance(gate, dict):
                    continue
                kind = "blocking" if gate.get("blocking") is True else "advisory"
                override = f"overridden ({gate['override']})" if gate.get("override") else "—"
                lines.append(
                    f"| {cell(name, token)} | {kind} | {cell(gate.get('status'), token)} "
                    f"| {cell(override, token)} |"
                )
        append(summary, "\n".join(lines) + "\n", token)
    print(f"AQEF outcome {outcome}.")
    return int(outcome == "fail")


if __name__ == "__main__":
    raise SystemExit(main())
