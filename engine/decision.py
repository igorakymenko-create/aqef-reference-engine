"""Decision and Release: I Chapter 6, Volumes X–XII, Appendices A/C."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid

from fastapi import HTTPException

from engine.assessment import clause_reference
from engine.auth import check_permission
from engine.composition import compose_scenario_effective_contract
from engine.models.contract import Contract
from engine.models.principal import ApprovalRecord, ApprovalStatus, AuditLogEntry, PrincipalKind
from engine.validators import canonical, number


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid.uuid4())


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def effective(rows):
    resolved = {r["resolves"] for r in rows if r.get("resolves")}
    return [r for r in rows if r["id"] not in resolved]


def result_state(entries):
    # awaiting_review completion keeps its id, but changes its assessed standing.
    return digest([{k:e["result"][k] for k in ("id", "disposition", "verdict", "confidence")} for e in entries])


def find_clause(record, reference):
    contract = record["configuration"]["contract"]
    for kind in ("constraints", "expectations"):
        for index, clause in enumerate(contract[kind]):
            if clause_reference(contract, kind, index) == reference:
                return clause
    raise HTTPException(409, "Result clause is absent from frozen Contract")


def govern(storage, principal, project, permission, target, details=None, person_only=False):
    check_permission(principal, permission, storage)
    if person_only and principal.kind != PrincipalKind.PERSON:
        raise HTTPException(403, f"{permission} requires a Person")
    roles = [storage.get_role(name) for name in principal.roles]
    role = next((r.name for r in roles if r and (permission in r.permissions or "admin" in r.permissions)), None)
    if role is None:
        raise HTTPException(403, f"No held Role grants {permission}")
    approver = principal.id
    if principal.kind == PrincipalKind.SERVICE_ACCOUNT and permission == "release_decide":
        policy = storage.decision_record("policy", project, (details or {}).get("release_policy", ""))
        if policy is None:
            raise HTTPException(403, "Standing release policy is required")
        approver = policy["approved_by"]
    approval = ApprovalRecord(id=identifier(), project=project, action=permission, target_resource=target,
                             requested_by=principal.id, approved_by=approver,
                             status=ApprovalStatus.APPROVED, details=details or {})
    storage.create_approval(approval)
    storage.create_audit_entry(AuditLogEntry(id=identifier(), project=project, action=permission,
        principal_id=principal.id, principal_kind=principal.kind,
        details={"target":target, "approval_id":approval.id, **(details or {})}))
    return {"approved_by":principal.id, "approved_at":now(), "approval_role":role}, approval.id


class DecisionEngine:
    def __init__(self, storage):
        self.store = storage

    def get(self, kind, project, key):
        value = self.store.decision_record(kind, project, key)
        if value is None:
            raise HTTPException(404, f"{kind} not found")
        return value

    def batch(self, project, batch):
        records = [r for r in self.store.list_executions(project) if r["execution_batch_id"] == batch]
        if not records and self.store.get_batch(project, batch) is None:
            raise HTTPException(404, "Execution batch not found")
        if any(r["status"] in ("queued", "running") for r in records):
            raise HTTPException(409, "Batch is still running")
        return records

    def batch_info(self, project, batch):
        saved = self.store.get_batch(project, batch)
        if saved:
            return saved
        records = self.batch(project, batch)
        return {"suite":records[0]["suite"], "environment":records[0]["environment"]}

    def scope(self, project, suites, environments):
        proj = self.store.get_project(project)
        if not proj:
            raise HTTPException(404, "Project not found")
        snapshot = {"project":project, "suites":sorted(set(suites)), "environments":{},
                    "contracts":{}, "inline_contracts":{}, "quality_gates":[],
                    "contract_contents":{}, "effective_contracts":{}}

        def collect(value, attachment):
            if isinstance(value, str):
                contract = self.store.get_contract(project, value)
                if contract is None:
                    raise HTTPException(409, f"Reusable Contract '{value}' cannot be resolved")
                if value in snapshot["contracts"]:
                    return
                snapshot["contracts"][value] = digest(contract.model_dump(mode="json"))
                snapshot["contract_contents"][value] = contract.model_dump(mode="json")
            else:
                contract = value
                if contract.name:
                    snapshot["contracts"][contract.name] = digest(contract.model_dump(mode="json"))
                    snapshot["contract_contents"][contract.name] = contract.model_dump(mode="json")
                else:
                    snapshot["inline_contracts"].setdefault(attachment, []).append(contract.model_dump(mode="json"))
            for name in contract.extends:
                collect(name, attachment)

        for env in sorted(set(environments)):
            config = self.store.get_environment(project, env)
            if config is None:
                raise HTTPException(409, "Scoped Environment no longer exists")
            snapshot["environments"][env] = config.model_dump(mode="json")
        for contract in proj.contracts:
            collect(contract, "project")
        snapshot["quality_gates"] = [g.model_dump(mode="json") for g in proj.quality_gates]
        for name in snapshot["suites"]:
            suite = self.store.get_suite(project, name)
            if suite is None:
                raise HTTPException(409, "Scoped Suite no longer exists")
            snapshot["quality_gates"].extend(g.model_dump(mode="json") for g in suite.quality_gates)
            for contract in suite.contracts:
                collect(contract, "suite:" + name)
            for scenario in suite.scenarios:
                if scenario.contract is not None:
                    collect(scenario.contract, f"scenario:{name}/{scenario.name}")
                try:
                    composed = compose_scenario_effective_contract(proj.contracts, suite.contracts, scenario.contract,
                                                                  lambda n:self.store.get_contract(project, n))
                except ValueError as exc:
                    raise HTTPException(409, str(exc)) from exc
                snapshot["effective_contracts"][f"{name}/{scenario.name}"] = composed.model_dump(mode="json")
        names = [g["name"] for g in snapshot["quality_gates"]]
        if len(names) != len(set(names)):
            raise HTTPException(409, "Quality Gate names must be unique across Project and Suites")
        return snapshot

    def snapshot(self, project, suites, environments, baselines=None, release_label=None):
        data = self.scope(project, suites, environments)
        data.update(id=identifier(), captured_at=now())
        if baselines is not None:
            for key in baselines:
                self.get("baseline", project, key)
            data["baselines"] = baselines
        else:
            data["baselines"] = [b["id"] for b in self.store.decision_records("baseline", project)
                                 if b["suite"] in suites and b["environment"] in environments]
        if release_label is not None:
            data["release_label"] = release_label
        return self.store.save_decision("snapshot", project, data)

    def current(self, snapshot):
        live = self.scope(snapshot["project"], snapshot["suites"], list(snapshot["environments"]))
        return all(live[k] == snapshot[k] for k in live)

    def entries(self, records, snapshot):
        entries = []
        for record in records:
            if record["configuration"]["scenario"]["seeded_control"] is not None:
                continue
            current = snapshot["effective_contracts"].get(record["suite"] + "/" + record["scenario"])
            for result in effective(self.store.list_results(record["project"], record["id"])):
                clause = find_clause(record, result["clause"])
                stale = record["configuration"]["environment"] != snapshot["environments"].get(record["environment"])
                if clause.get("id"):
                    other = next((c for kind in ("constraints", "expectations") for c in (current or {}).get(kind, [])
                                  if c.get("id") == clause["id"]), None)
                    stale = stale or other != clause
                else:
                    stale = stale or current != record["configuration"]["contract"]
                weight = ((current or record["configuration"]["contract"]).get("policies") or {}).get("weight")
                weight = 1 if weight is None else number(weight)
                if weight <= 0:
                    raise HTTPException(422, "Contract weight must be positive for aggregation")
                entries.append({"record":record, "result":result, "clause":clause, "stale":stale, "weight":weight})
        return entries

    def comparable_baseline(self, project, gate, entry):
        target = gate.get("compare_against")
        if not target:
            return None
        baselines = self.store.decision_records("baseline", project)
        snapshot = self.store.decision_record("snapshot", project, target)
        if snapshot:
            baselines = [b for b in baselines if b["id"] in snapshot.get("baselines", [])]
        elif target != "latest_approved":
            baselines = [b for b in baselines if b["id"] == target or b.get("name") == target]
        matching = [b for b in baselines if b["suite"] == entry["record"]["suite"] and
                    b["scenario"] == entry["record"]["scenario"] and b["result"]["clause"] == entry["result"]["clause"]
                    and b["result"]["oracle"] == entry["result"]["oracle"]]
        return matching[-1] if matching else None

    def gate(self, project, definition, entries, records, snapshot):
        dimension = definition["aggregate"]
        threshold = definition["threshold"]
        dimensions = {"functional", "semantic", "safety", "operational"}
        if dimension not in dimensions | {"overall", "regression"}:
            raise HTTPException(422, "Unsupported aggregate: " + dimension)
        relevant = [e for e in entries if dimension in ("overall", "regression") or e["clause"]["dimension"] == dimension]
        selected = set(threshold) & dimensions if isinstance(threshold, dict) else set()
        if dimension == "overall" and selected:
            relevant = [e for e in relevant if e["clause"]["dimension"] in selected]
        reasons = set()
        usable = []
        for entry in relevant:
            r = entry["result"]
            bad = False
            if r["disposition"] != "actionable":
                reasons.add("non_actionable_results")
                bad = True
            if entry["stale"]:
                reasons.add("stale_results")
                bad = True
            if definition["require_admitted_judges"] and r["oracle_type"] == "judge" and not self.store.is_admitted(project, r["oracle"]):
                reasons.add("judge_not_admitted")
                bad = True
            if not bad:
                usable.append(entry)
        # Missing newly-applicable clauses and failed collection cannot create a green Gate.
        expected_missing = False
        for record in records:
            if record["configuration"]["scenario"]["seeded_control"] is not None:
                continue
            current = snapshot["effective_contracts"].get(record["suite"] + "/" + record["scenario"], {})
            present = {e["result"]["clause"] for e in entries if e["record"]["id"] == record["id"]}
            for kind in ("constraints", "expectations"):
                for index, clause in enumerate(current.get(kind, [])):
                    if (dimension in ("overall", "regression") or clause["dimension"] == dimension) and clause_reference(current, kind, index) not in present:
                        expected_missing = True
        if expected_missing:
            reasons.add("insufficient_basis")
        recorded_scenarios = {r["suite"] + "/" + r["scenario"] for r in records}
        for name, contract in snapshot["effective_contracts"].items():
            if name not in recorded_scenarios and any(dimension in ("overall", "regression") or c["dimension"] == dimension
                for kind in ("constraints", "expectations") for c in contract[kind]):
                reasons.add("insufficient_basis")
        basis = {"results":len(usable), "not_actionable":len(relevant)-len(usable),
                 "scenarios":len({(e["record"]["suite"], e["record"]["scenario"]) for e in usable}),
                 "executions":len({e["record"]["id"] for e in usable}), "min_basis_met":"not_declared"}
        minimum = definition.get("min_basis")
        if minimum:
            basis["min_basis_met"] = all(basis[key] >= value for key, value in minimum.items() if value is not None)
            if not basis["min_basis_met"]:
                reasons.add("insufficient_basis")

        def rate(rows):
            return sum(e["weight"] * (e["result"]["verdict"] == "pass") for e in rows) / sum(e["weight"] for e in rows) if rows else None

        def metric(key):
            if key == "overall":
                parts = []
                configured = [k for k in threshold if k in dimensions] if isinstance(threshold, dict) else []
                for d in configured or sorted(dimensions):
                    value = rate([e for e in usable if e["clause"]["dimension"] == d])
                    bound = threshold.get(d, {}) if isinstance(threshold, dict) else {}
                    weight = bound.get("weight", 1) if isinstance(bound, dict) else 1
                    if isinstance(weight, bool) or not isinstance(weight, (int,float)) or weight <= 0:
                        raise HTTPException(422, "Dimension weight must be positive")
                    if value is not None:
                        parts.append((value, weight))
                return sum(v*w for v,w in parts)/sum(w for v,w in parts) if parts else None
            if key in dimensions:
                return rate([e for e in usable if e["clause"]["dimension"] == key])
            if key == "pass_rate":
                if dimension == "regression":
                    compared = [(e, self.comparable_baseline(project, definition, e)) for e in usable]
                    if not compared or any(b is None for e,b in compared):
                        return None
                    return sum(e["weight"] * (b["result"]["verdict"] == "pass" and e["result"]["verdict"] == "fail")
                               for e,b in compared) / sum(e["weight"] for e,b in compared)
                if dimension == "overall":
                    return metric("overall")
                return rate(usable)
            unique = {e["record"]["id"]:e["record"] for e in usable}
            if not unique:
                return None
            if key == "latency_ms":
                return sum(r["duration_ms"] for r in unique.values())/len(unique)
            if key in ("total_tokens", "cost"):
                values = [a["data"].get(key) for r in unique.values() for a in r["artifacts"]
                          if a["name"] == "usage" and isinstance(a["data"], dict)]
                return sum(number(v) for v in values)/len(unique) if values and all(v is not None for v in values) else None
            raise HTTPException(422, "Unsupported threshold metric: " + key)

        thresholds = threshold if isinstance(threshold, dict) else {"pass_rate":threshold}
        if not thresholds:
            raise HTTPException(422, "ThresholdMap cannot be empty")
        values = {}
        metric_basis = {}
        for key, bound in thresholds.items():
            try:
                if isinstance(bound, dict):
                    if not set(bound) <= {"min", "max", "weight"} or not ({"min", "max"} & set(bound)):
                        raise ValueError("Expected min/max/weight bounds")
                    for v in bound.values():
                        number(v)
                    if "weight" in bound and (bound["weight"] <= 0 or key not in dimensions or "overall" not in thresholds):
                        raise ValueError("Dimension weight must be positive and used with an overall threshold")
                else:
                    number(bound)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            value = metric(key)
            counted = [e for e in usable if key not in dimensions or e["clause"]["dimension"] == key]
            scoped = [e for e in relevant if key not in dimensions or e["clause"]["dimension"] == key]
            sub_basis = {"results":len(counted), "not_actionable":len(scoped)-len(counted),
                         "scenarios":len({(e["record"]["suite"], e["record"]["scenario"]) for e in counted}),
                         "executions":len({e["record"]["id"] for e in counted}), "min_basis_met":"not_declared"}
            if minimum:
                sub_basis["min_basis_met"] = all(sub_basis[k] >= v for k,v in minimum.items() if v is not None)
                if not sub_basis["min_basis_met"]:
                    basis["min_basis_met"] = False
                    reasons.add("insufficient_basis")
            metric_basis[key] = sub_basis
            values[key] = "not_computed" if value is None else value
            if value is None:
                reasons.add("insufficient_basis")
                continue
            if isinstance(bound, dict):
                failed = ("min" in bound and value < bound["min"]) or ("max" in bound and value > bound["max"])
            else:
                failed = value > bound if key in ("latency_ms", "total_tokens", "cost") or dimension == "regression" else value < bound
            if failed:
                reasons.add("threshold")
        # Deterministic Safety failures remain a veto separate from numerical means.
        if any((e["clause"]["dimension"] == "safety" or e["clause"].get("veto")) and e["result"]["oracle_type"] == "validator" and
               e["result"]["verdict"] == "fail" for e in relevant):
            reasons.add("threshold")
        result = {"id":identifier(), "status":"fail" if reasons else "pass",
                  "blocking":definition["on_failure"] == "block_release", "threshold":deepcopy(threshold),
                  "value":values if isinstance(threshold, dict) else values["pass_rate"], "basis":basis}
        if reasons:
            result["reasons"] = sorted(reasons)
        if isinstance(threshold, dict):
            result["metric_basis"] = metric_basis
        return result

    def evaluate(self, project, batch):
        records = self.batch(project, batch)
        info = self.batch_info(project, batch)
        suites = [info["suite"]]
        envs = [info["environment"]]
        snapshot = self.snapshot(project, suites, envs)
        entries = self.entries(records, snapshot)
        gates = {g["name"]:self.gate(project, g, entries, records, snapshot) for g in snapshot["quality_gates"]}
        data = {"id":snapshot["id"], "snapshot_id":snapshot["id"], "execution_batch_id":batch,
                "gates":gates, "result_ids":[e["result"]["id"] for e in entries], "evaluated_at":now(),
                "result_state":result_state(entries),
                "admissions":{e["result"]["oracle"]:self.store.is_admitted(project, e["result"]["oracle"])
                              for e in entries if e["result"]["oracle_type"] == "judge"}}
        self.store.save_decision("evaluation", project, data)
        return data

    def overridden(self, project, gates):
        gates = deepcopy(gates)
        for result in gates.values():
            override = self.store.decision_record("override", project, result["id"])
            if override:
                result["override"] = override["approval_id"]
        return gates

    def report(self, project, batch):
        records = self.batch(project, batch)
        evaluations = [e for e in self.store.decision_records("evaluation", project) if e["execution_batch_id"] == batch]
        evaluation = evaluations[-1] if evaluations else self.evaluate(project, batch)
        snapshot = self.get("snapshot", project, evaluation["snapshot_id"])
        if not self.current(snapshot):
            evaluation = self.evaluate(project, batch)
            snapshot = self.get("snapshot", project, evaluation["snapshot_id"])
        entries = self.entries(records, snapshot)
        admissions = {e["result"]["oracle"]:self.store.is_admitted(project, e["result"]["oracle"])
                      for e in entries if e["result"]["oracle_type"] == "judge"}
        if result_state(entries) != evaluation["result_state"] or admissions != evaluation["admissions"]:
            evaluation = self.evaluate(project, batch)
        signals = {key:[] for key in ("retries", "low_confidence", "multi_judge", "unenforced_boundaries", "boundary_attempts", "unadmitted_judges")}
        signals["unenforced_boundaries"] = sorted(name for name,env in snapshot["environments"].items()
                                                  if env.get("action_boundary") and not env["action_boundary"]["enforced"])
        retries = {}
        lows = {}
        unadmitted = set()
        for record in records:
            scenario = record["suite"] + "/" + record["scenario"]
            retries[scenario] = retries.get(scenario, 0) + record["retry_count"]
            for r in self.store.list_results(project, record["id"]):
                key = (scenario, r["oracle"])
                count = lows.setdefault(key, [0, 0])
                count[0] += r["disposition"] == "inconclusive"
                count[1] += 1
                if r["oracle_type"] == "judge" and not self.store.is_admitted(project, r["oracle"]):
                    unadmitted.add(r["oracle"])
            boundary = record["configuration"]["environment"].get("action_boundary")
            if boundary and not boundary["enforced"] and record["environment"] not in signals["unenforced_boundaries"]:
                signals["unenforced_boundaries"].append(record["environment"])
            for artifact in record["artifacts"]:
                attempts = artifact["data"] if artifact["name"] == "boundary_attempts" else [artifact["data"]] if artifact["name"] == "boundary_attempt" else []
                if isinstance(attempts, list):
                    for attempt in attempts:
                        if isinstance(attempt, dict) and "target" in attempt:
                            signals["boundary_attempts"].append({**deepcopy(attempt), "execution":record["id"]})
        signals["retries"] = [{"scenario":k, "retries":v} for k,v in retries.items() if v]
        signals["low_confidence"] = [{"scenario":k[0], "oracle":k[1], "inconclusive":v[0], "results":v[1]} for k,v in lows.items()]
        signals["unadmitted_judges"] = sorted(unadmitted)
        metrics = []
        for dimension in ("functional", "semantic", "safety", "operational"):
            rows = [e for e in entries if e["clause"]["dimension"] == dimension and not e["stale"] and e["result"]["disposition"] == "actionable"]
            value = sum(e["weight"]*(e["result"]["verdict"] == "pass") for e in rows)/sum(e["weight"] for e in rows) if rows else "not_computed"
            metrics.append({"name":dimension + ".pass_rate", "definition":"Contract-weighted actionable pass rate; Confidence applied before aggregation",
                            "value":value, "result_ids":[e["result"]["id"] for e in rows]})
        for entry in entries:
            if entry["stale"] or entry["result"]["disposition"] != "actionable":
                continue
            baseline = self.comparable_baseline(project, {"compare_against":"latest_approved"}, entry)
            if baseline:
                before = baseline["configuration"]
                after = entry["record"]["configuration"]
                causes = []
                if before["environment"]["model_version"] != after["environment"]["model_version"]:
                    causes.append("model_drift")
                if (before["environment"]["prompt_version"], before["scenario"]["prompt"]) != (after["environment"]["prompt_version"], after["scenario"]["prompt"]):
                    causes.append("prompt_drift")
                if baseline["dataset"] != entry["record"]["dataset"]:
                    causes.append("dataset_drift")
                metrics.append({"name":"regression_comparison", "definition":"Same Oracle/clause baseline pass to current fail, independent of response text",
                    "value":int(baseline["result"]["verdict"] == "pass" and entry["result"]["verdict"] == "fail"),
                    "result_ids":[baseline["result_id"], entry["result"]["id"]], "baseline_id":baseline["id"], "possible_causes":causes})
        data = {"id":identifier(), "generated_at":now(), "scope":{"project":project,
                "suites":snapshot["suites"], "environments":list(snapshot["environments"]), "execution_batch_ids":[batch]},
                "snapshot_id":evaluation["snapshot_id"], "gates":self.overridden(project, evaluation["gates"]),
                "metrics":metrics, "signals":signals}
        return self.store.save_decision("report", project, data)
