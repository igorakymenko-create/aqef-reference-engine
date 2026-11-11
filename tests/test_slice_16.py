"""Volume XIII Action checks against the live engine and SDK."""

from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
import time

import pytest
import yaml

from aqef_client import APIError, Client
from test_slice_13 import live, definition, TOKEN


ROOT = Path(__file__).resolve().parents[1]
CI_TOKEN = "slice16-example-service-token"


def provision(url):
    with Client(url, TOKEN) as client:
        client.create_role({"name": "ci16", "permissions": ["read", "execute", "release_decide"]})
        client.create_principal({
            "id": "ci16", "name": "CI", "kind": "service_account", "owner_person_id": "admin",
            "roles": ["ci16"], "token": CI_TOKEN,
        })


@pytest.fixture(scope="module")
def ci_engine(live):
    url = live[0]
    provision(url)
    return url


def prepare(url, name, *, passing=False, advisory=False, double=False, human=False, policy=False):
    config = definition(name, passing=passing)
    gate = config["quality_gates"][0]
    if advisory:
        gate["on_failure"] = "warn"
    if double:
        config["quality_gates"].append(gate | {"name": "other"})
    if human:
        config["contracts"][0]["constraints"] = []
        config["contracts"][0]["expectations"] = [{
            "id": "review", "criteria": "Approve the response",
            "human_reviewer": {"role": "admin"},
        }]
        gate["aggregate"] = "semantic"
    with Client(url, TOKEN) as admin:
        admin.create_project(config)
        release_policy = admin.approve_release_policy(name, {
            "suites": ["s"], "environments": ["test"], "service_accounts": ["ci16"],
        }).json()["id"] if policy else ""
    return release_policy


def start(url, tmp_path, name, *, batch="", policy="", wait="2"):
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    env = os.environ | {
        "PYTHONPATH": str(ROOT / "client"), "AQEF_URL": url, "AQEF_TOKEN": CI_TOKEN,
        "AQEF_PROJECT": name, "AQEF_SUITE": "s", "AQEF_ENVIRONMENT": "test",
        "AQEF_BATCH": batch, "AQEF_RELEASE_POLICY": policy, "AQEF_WAIT_TIMEOUT": wait,
        "AQEF_POLL_INTERVAL": "0.05", "GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "aqef_client.ci.github"], env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return process, output, summary


def collect(run, expected):
    process, output, summary = run
    stdout, stderr = process.communicate(timeout=15)
    assert process.returncode == int(expected == "fail"), (stdout, stderr, summary.read_text() if summary.exists() else "")
    report = summary.read_text(encoding="utf-8")
    data = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    assert data["outcome"] == expected
    assert CI_TOKEN not in stdout + stderr + report + output.read_text(encoding="utf-8")
    return data["execution_batch"], report


def evaluation(client, name, *, batch=None):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        snapshots = client.list_snapshots(name).json()
        for snapshot in reversed(snapshots):
            try:
                data = client.get_gate_evaluation(name, snapshot["id"]).json()
            except APIError as exc:
                if exc.status_code != 404:
                    raise
                continue
            if batch is None or data["execution_batch_id"] == batch:
                return data
        time.sleep(0.03)
    pytest.fail("Action did not publish its Gate evaluation")


def override(client, project, view, gate="functional"):
    return client.override_gate(project, gate, {
        "execution_batch_id": view["execution_batch_id"], "gate_result_id": view["gates"][gate]["id"],
        "justification": "Person approved the exception",
    }).json()["approval_id"]


@pytest.mark.parametrize("passing,advisory,expected", [
    (True, False, "pass"), (False, False, "fail"), (False, True, "pass"),
])
def test_xiii_native_step_status_and_summary(ci_engine, tmp_path, passing, advisory, expected):
    name = f"ci-status-{passing}-{advisory}"
    prepare(ci_engine, name, passing=passing, advisory=advisory)
    batch, report = collect(start(ci_engine, tmp_path, name), expected)
    assert batch
    assert f"| functional | {'advisory' if advisory else 'blocking'} | {'pass' if passing else 'fail'} |" in report


@pytest.mark.parametrize("double", [False, True])
def test_xiii_reads_own_override_and_leaves_other_blocking_failure(ci_engine, tmp_path, double):
    name = f"ci-override-{double}"
    policy = prepare(ci_engine, name, double=double, policy=True)
    run = start(ci_engine, tmp_path, name, policy=policy, wait="5")
    with Client(ci_engine, TOKEN) as admin:
        view = evaluation(admin, name)
        approval = override(admin, name, view)
        batch, summary = collect(run, "fail" if double else "pass_with_override")
        assert batch == view["execution_batch_id"]
        assert f"| functional | blocking | fail | overridden ({approval}) |" in summary
        if double:
            assert "| other | blocking | fail | — |" in summary
        assert admin.list_releases(name).json() == []
        assert len(admin.list_snapshots(name).json()) == 1


def test_xiii_earlier_batch_override_does_not_count(ci_engine, tmp_path):
    name = "ci-earlier"
    prepare(ci_engine, name)
    with Client(ci_engine, TOKEN) as admin:
        old = admin.trigger_execution(name, {"suite": "s", "environment": "test"}).json()["execution_batch_id"]
        view = admin.check_gates(name, {"execution_batch_id": old}).json()
        approval = override(admin, name, view)
        batch = admin.trigger_execution(name, {"suite": "s", "environment": "test"}).json()["execution_batch_id"]
    actual, summary = collect(start(ci_engine, tmp_path, name, batch=batch), "fail")
    assert actual == batch and actual != old and approval not in summary


def test_xii_unchanged_evaluation_check_does_not_append_audit(ci_engine):
    name = "ci-unchanged"
    prepare(ci_engine, name, passing=True)
    with Client(ci_engine, TOKEN) as admin:
        batch = admin.trigger_execution(name, {"suite": "s", "environment": "test"}).json()["execution_batch_id"]
        view = admin.check_gates(name, {"execution_batch_id": batch}).json()
        before = admin.get_audit_log(name).json()
        unchanged = admin.check_gates(name, {
            "execution_batch_id": batch, "previous_evaluation_id": view["snapshot_id"],
        }).json()
        assert unchanged["snapshot_id"] == view["snapshot_id"]
        assert admin.get_audit_log(name).json() == before


@pytest.mark.parametrize("resolve", [False, True])
def test_xiii_awaiting_review_is_bounded_and_resolved_evidence_is_refreshed(
    ci_engine, tmp_path, resolve,
):
    name = f"ci-review-{resolve}"
    prepare(ci_engine, name, human=True)
    with Client(ci_engine, TOKEN) as admin:
        triggered = admin.trigger_execution(name, {"suite": "s", "environment": "test"}).json()
        batch = triggered["execution_batch_id"]
        started = time.monotonic()
        run = start(ci_engine, tmp_path, name, batch=batch, wait="5" if resolve else "1.2")
        if resolve:
            initial = evaluation(admin, name, batch=batch)
            assert initial["gates"]["functional"]["status"] == "fail"
            for execution in triggered["executions"]:
                row = admin.list_results(name, execution["id"]).json()[0]
                assert row["disposition"] == "awaiting_review"
                admin.review_result(name, execution["id"], row["id"], {
                    "verdict": "pass", "supporting_evidence": "Reviewed",
                })
        actual_batch, summary = collect(run, "pass" if resolve else "fail")
        finished_at = datetime.now(timezone.utc)
        if not resolve:
            assert 1.0 <= time.monotonic() - started < 5
            assert "timeout" in summary
        else:
            snapshots = admin.list_snapshots(name).json()
            assert all(datetime.fromisoformat(row["captured_at"]) <= finished_at for row in snapshots)
            final = admin.get_gate_evaluation(name, snapshots[-1]["id"]).json()
            assert final["id"] != initial["id"]
            assert final["execution_batch_id"] == actual_batch == batch
            assert final["gates"]["functional"]["status"] == "pass"
            assert "| functional | blocking | pass |" in summary


def test_xii_ci_records_release_using_service_policy(ci_engine, tmp_path):
    name = "ci-release"
    policy = prepare(ci_engine, name, passing=True, policy=True)
    batch, summary = collect(start(ci_engine, tmp_path, name, policy=policy), "pass")
    with Client(ci_engine, TOKEN) as admin:
        release, = admin.list_releases(name).json()
        assert release["execution_batch_id"] == batch
        assert release["release_policy"] == policy and release["decision"] == "approved"
        assert release["approved_by"] == "ci16"
    assert "Release Decision recorded" in summary


def test_xiii_action_and_example_yaml():
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    workflow = yaml.load((ROOT / ".github/workflows/aqef-example.yml").read_text(encoding="utf-8"),
                         Loader=yaml.BaseLoader)
    assert action["runs"]["using"] == "composite"
    assert set(action["outputs"]) == {"execution-batch", "outcome"}
    assert set(workflow["on"]) == {"pull_request", "workflow_dispatch"}
    assert any(step.get("uses") == "./" for step in workflow["jobs"]["quality"]["steps"])
