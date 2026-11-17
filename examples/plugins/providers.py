"""Run with uvicorn providers:app --app-dir examples/plugins --port 9200."""

import asyncio
import uuid

from fastapi import FastAPI, HTTPException, Response


app = FastAPI()


def result(body, oracle, kind, confidence, supporting):
    return {"id": body["execution"] + "/" + body["clause"],
            "execution": body["execution"], "clause": body["clause"],
            "oracle": oracle, "oracle_type": kind, "verdict": "pass",
            "confidence": confidence, "disposition": "actionable",
            "recorded_at": "2026-01-01T00:00:00Z", "supporting_evidence": supporting}


@app.post("/validator")
async def validator(body: dict):
    assert set(body) == {"evidence", "expected", "configuration", "execution", "clause"}
    config = body["configuration"]
    reply = result(body, config["oracle"], "validator", "not_applicable", {"observed": body["evidence"]})
    mode = config.get("mode")
    if mode == "variable":
        reply["supporting_evidence"] = str(uuid.uuid4())
    if body["execution"] != "repeatability-probe":
        if mode == "crash":
            raise HTTPException(500)
        if mode == "timeout":
            await asyncio.sleep(2)
        if mode == "nonjson":
            return Response("not JSON")
        if mode == "malformed":
            reply.pop("verdict")
        if mode == "confidence":
            reply["confidence"] = 0.9
        if mode == "extra":
            reply["mutate"] = {"action": "delete_project"}
    return reply


@app.post("/judge")
def judge(body: dict):
    assert set(body) == {"evidence", "criteria", "configuration", "execution", "clause"}
    config = body["configuration"]
    reply = result(body, config["oracle"], "judge", config.get("confidence", 0.9),
                   {"criteria": body["criteria"]})
    if config.get("mode") == "confidence":
        reply.pop("confidence")
    if config.get("mode") == "criteria":
        reply["supporting_evidence"] = {}
    return reply


@app.post("/dataset")
def dataset(body: dict):
    assert set(body) in ({"name", "version", "configuration"}, {"name", "version", "configuration", "base_dataset"})
    if body["configuration"].get("mode") == "invalid":
        return {"rows": [{"variables": {}}]}
    return {"rows": [{"id": "one", "variables": {"who": "plugin"}}]}


@app.post("/report")
def report(body: dict):
    assert set(body) == {"results", "configuration"}
    return {"name": "count", "value": len(body["results"]),
            "result_ids": [] if body["configuration"].get("missing") else [r["id"] for r in body["results"]]}
