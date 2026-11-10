"""Execution-time tool dispatch and live Evidence collection."""

import asyncio
from copy import deepcopy
import json
import time

from engine.tool_boundary import argument_errors, decide_boundary


TOOL_LIMIT = 16


class ToolRuntime:
    def __init__(self, storage, executor, record):
        self.storage = storage
        self.executor = executor
        self.record = record
        environment = record["configuration"]["environment"]
        config = environment.get("tool_configuration") or {}
        self.tools = {tool["name"]: tool["parameters"] for tool in config.get("tools", [])}
        self.boundary = environment.get("action_boundary")
        self.count = 0

    def artifact(self, name, data, turns):
        self.record["artifacts"].append(
            {"name": name, "data": deepcopy(data), "turn": len(turns)},
        )

    def checkpoint(self, turns):
        self.record["partial_turns"] = deepcopy(turns)
        self.storage.update_execution(self.record)

    async def handle(self, calls, turns, deadline):
        for index, call in enumerate(calls):
            name = call["name"]
            arguments = call["arguments"]
            kind, targets, denied, tripwires = decide_boundary(
                name, arguments, self.boundary, declared=name in self.tools,
            )
            call["targets"] = targets
            call["kind"] = kind
            self.count += 1
            over_limit = self.count > TOOL_LIMIT
            errors = argument_errors(arguments, self.tools[name]) if name in self.tools else []
            if over_limit or denied or errors:
                call.update(status="refused", result={
                    "error": "step_limit" if over_limit else "boundary_denied" if denied else "invalid_arguments",
                })
            elif kind == "stub":
                call.update(status="stub", result={"status": "stubbed"})
            else:
                call["status"] = "pending"
            for target in denied:
                self.artifact("boundary_attempt", {
                    "target": target, "blocked": True, "tripwire": False,
                }, turns)
            for target in tripwires:
                self.artifact("boundary_attempt", {
                    "target": target, "blocked": call["status"] == "refused", "tripwire": True,
                }, turns)
            # Persist the authorized or refused invocation before any dispatch.
            self.artifact("tool_call", call, turns)
            self.checkpoint(turns)
            if call["status"] != "pending":
                continue
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Execution deadline exceeded")
                if kind not in self.executor.urls:
                    raise ValueError("No executor configured for this tool boundary kind")
                reply = await asyncio.wait_for(
                    self.executor.call(kind, {
                        "execution": self.record["id"], "kind": kind,
                        "name": name, "arguments": arguments, "targets": targets,
                    }, remaining, strict_json=True), remaining,
                )
                if not isinstance(reply, dict) or set(reply) != {"result"}:
                    raise ValueError("Malformed tool executor response")
                json.dumps(reply, allow_nan=False, ensure_ascii=False).encode("utf-8")
                call.update(status="completed", result=reply["result"])
            except Exception:
                call.update(status="infrastructure_failure", result={"error": "tool_executor_failure"})
                self.artifact("tool_result", call, turns)
                self.checkpoint(turns)
                # Record the remaining requests without dispatching them.
                for unhandled in calls[index + 1:]:
                    self.refuse_after_failure(unhandled, turns)
                raise RuntimeError("Tool executor failed or timed out") from None
            self.artifact("tool_result", call, turns)
            self.checkpoint(turns)
        if self.count > TOOL_LIMIT:
            raise RuntimeError("Tool step limit exceeded")

    def refuse_after_failure(self, call, turns):
        _, targets, denied, tripwires = decide_boundary(
            call["name"], call["arguments"], self.boundary, declared=call["name"] in self.tools,
        )
        call.update(targets=targets, kind=None, status="refused", result={"error": "execution_aborted"})
        for target, tripwire in [(t, False) for t in denied] + [(t, True) for t in tripwires]:
            self.artifact("boundary_attempt", {"target": target, "blocked": True, "tripwire": tripwire}, turns)
        self.artifact("tool_call", call, turns)
        self.checkpoint(turns)
