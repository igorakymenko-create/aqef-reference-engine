"""Scoped Oracles and run-level instrument evidence (Volumes VI/VIII)."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math

from fastapi import HTTPException

from engine.assessment import judge_identity, result_base, timestamp
from engine.validators import canonical


def control_key(record):
    return record["execution_batch_id"]+":"+record["suite"]+"/"+record["scenario"]


def lookup_result(store, project, key):
    member=store.decision_record("member_result",project,key)
    if member:return member
    for record in store.list_executions(project):
        for row in store.list_results(project,record["id"]):
            if row["id"]==key:return row
    return None


def panel_identity(clause):
    return canonical({"type":"multi_judge","version":"panel-v1","criteria":clause["criteria"],"configuration":clause["multi_judge"]})


def scored_at(result):
    return result["supporting_evidence"].get("reviewed_at",result["recorded_at"])


def clause_classes(clause):
    return clause.get("defect_classes") or None


def control_view(store, project, base):
    data=deepcopy(base)
    human=store.decision_record("control_confirmation",project,data["id"])
    confirmed=data["confirmed"] or human is not None
    if data.get("needs_reference_review") and human is None:confirmed=False
    data["confirmed"]=confirmed
    by_oracle={};assessed=[]
    roots=data.get("root_assessments",data["assessments"])
    for ref in roots:
        row=lookup_result(store,project,ref)
        if row is None:continue
        while row["disposition"]=="oracle_unavailable":
            next_row=next((r for r in store.list_results(project,row["execution"]) if r.get("resolves")==row["id"] and r["oracle"]==row["oracle"]),None)
            if next_row is None:break
            row=next_row
        assessed.extend([row]+row["supporting_evidence"].get("member_results",[]))
    data["assessments"]=[r["id"] for r in assessed]
    for row in assessed:by_oracle.setdefault(row["oracle"],[]).append(row)
    outcomes=[];miss_times=[]
    for oracle,rows in by_oracle.items():
        expected="fail" if data["kind"]=="defect" else "pass"
        if not confirmed or any(r["verdict"] is None for r in rows):outcome="invalid"
        elif all(r["verdict"]==expected and r["disposition"]=="actionable" for r in rows):
            outcome="caught" if data["kind"]=="defect" else "passed"
        else:outcome="missed" if data["kind"]=="defect" else "false_alarm"
        if outcome in ("missed","false_alarm"):miss_times.extend(scored_at(r) for r in rows)
        outcomes.append({"oracle":oracle,"outcome":outcome,"result_ids":[r["id"] for r in rows]})
    data["oracles"]=outcomes
    miss=any(o["outcome"] in ("missed","false_alarm") for o in outcomes)
    data["outcome"]=("missed" if data["kind"]=="defect" else "false_alarm") if miss else (
        "invalid" if not outcomes or any(o["outcome"]=="invalid" for o in outcomes) else "caught" if data["kind"]=="defect" else "passed")
    if miss:data["miss_recorded_at"]=max([data["recorded_at"],human["recorded_at"] if human else data["recorded_at"]]+miss_times,key=datetime.fromisoformat)
    full=store.decision_record("full_invalidation",project,data["id"])
    full_reason=(full or {}).get("reason") or ("halt_run" if miss and data["policy"]=="halt_run" else None)
    data["invalidation_scope"]="full_run" if miss and full_reason else "defect_class" if miss else "none"
    data["reason"]=full_reason if data["invalidation_scope"]=="full_run" else None
    if human:data["confirmation_record"]=human
    return data


def controls(store, project, batch=None):
    return [control_view(store,project,c) for c in store.decision_records("control",project)
            if batch is None or c["execution_batch_id"]==batch]


def missed_by(control, oracle):
    return any(o["oracle"]==oracle and o["outcome"] in ("missed","false_alarm") for o in control["oracles"])


def blocked_by(store, record, oracle, clause):
    classes=clause_classes(clause)
    return [c for c in controls(store,record["project"]) if missed_by(c,oracle) and
            (classes is None or c["defect_class"] in classes)]


def blocked_result(store, record, clause, reference, kind, oracle, persist=True):
    blocked=blocked_by(store,record,oracle,clause)
    if not blocked:return None
    result=result_base(record,reference,kind,oracle,{"blocked_by":[{"control_id":c["id"],"scenario":c["scenario"],
        "defect_class":c["defect_class"],"kind":c["kind"],"execution_batch_id":c["execution_batch_id"]} for c in blocked]})
    result["disposition"]="not_assessed"
    return store.append_result(record["project"],result) if persist else result


def qualification_requirements(store, record, result):
    refs=invalidators(store,record["project"],result)
    ids={x["control_id"] for x in result["supporting_evidence"].get("blocked_by",[])}
    ids.update(x["control_id"] for m in result["supporting_evidence"].get("member_results",[])
               for x in m["supporting_evidence"].get("blocked_by",[]))
    return [c for c in controls(store,record["project"]) if c["id"] in ids or (
        c["execution_batch_id"]==record["execution_batch_id"] and any(
            r["scenario"]==c["scenario"] and r["defect_class"]==c["defect_class"] for r in refs))]


def qualifications_for(store, record, previous, oracle):
    required=qualification_requirements(store,record,previous)
    if not required:raise HTTPException(409,"Result has no control miss requiring requalification")
    for defect in {c["defect_class"] for c in required}:
        kinds={c["kind"] for c in required if c["defect_class"]==defect}
        qualified=set()
        for q in store.decision_records("requalification",record["project"]):
            if q["oracle"]!=oracle or q["defect_class"]!=defect:continue
            for key in q["controls"]:
                for control in controls(store,record["project"]):
                    if key not in control["assessments"]:continue
                    scored=lookup_result(store,record["project"],key)
                    if scored is None or any(datetime.fromisoformat(scored_at(scored))<=datetime.fromisoformat(c.get("miss_recorded_at",c["recorded_at"])) for c in required):
                        raise HTTPException(409,"Requalification requires fresh controls scored after the affected misses")
                    if any((control["suite"],control["scenario"])==(c["suite"],c["scenario"]) or
                           (control.get("source_execution") and control.get("source_execution")==c.get("source_execution")) or
                           control.get("evidence_fingerprint")==c.get("evidence_fingerprint") for c in required):
                        raise HTTPException(409,"Requalification control was exposed by the affected run")
                    if any(o["oracle"]==oracle and key in o["result_ids"] and o["outcome"] in ("caught","passed") for o in control["oracles"]):
                        qualified.add(control["kind"])
        if not kinds<=qualified:raise HTTPException(409,f"Requalification missing required fresh control kinds for class '{defect}'")
    return [c["id"] for c in required]


def invalidators(store, project, result):
    record=store.get_execution(project,result["execution"])
    if not record or record["configuration"]["scenario"]["seeded_control"] is not None:return []
    from engine.decision import find_clause
    clause=find_clause(record,result["clause"])
    classes=clause_classes(clause)
    support=result["supporting_evidence"]
    exempt=set(support.get("requalified_controls",[]))
    identities=set() if support.get("member_results") else {result["oracle"]}
    for member in support.get("member_results",[]):
        if member["disposition"]!="not_assessed" or result["disposition"]=="not_assessed":identities.add(member["oracle"])
    found=[]
    for c in controls(store,project,record["execution_batch_id"]):
        if c["id"] in exempt:continue
        if c["invalidation_scope"]=="full_run" or ((classes is None or c["defect_class"] in classes) and any(missed_by(c,o) for o in identities)):
            found.append({"scenario":c["scenario"],"defect_class":c["defect_class"]})
    return found


def clock_now():
    return datetime.now(timezone.utc)


def review_route(result):
    if result["oracle_type"]!="human_reviewer" or result["disposition"]!="awaiting_review":return None
    from engine.execution import duration
    config=result["supporting_evidence"].get("review",{})
    elapsed=(clock_now()-datetime.fromisoformat(result["recorded_at"])).total_seconds()
    expired=elapsed>=duration(config.get("timeout","24h"))
    role=config.get("role")
    state="pending"
    if expired:
        state="escalated" if config.get("on_timeout")=="escalate" else "timed_out"
        if state=="escalated":role=config.get("escalate_to")
    return {"role":role,"state":state,"captures_confidence":config.get("captures_confidence",False),
            "timeout":config.get("timeout","24h")}


def decorate_result(store, project, row):
    result=deepcopy(row)
    invalid=invalidators(store,project,result)
    if invalid:result["invalidated_by"]=invalid
    routing=review_route(result)
    if routing:
        required=[routing["role"]] if routing["role"] else []
        record=store.get_execution(project,result["execution"])
        if record:
            from engine.decision import find_clause
            role=(find_clause(record,result["clause"]).get("human_reviewer") or {}).get("role")
            if role and role not in required and routing["state"]!="escalated":required.append(role)
        routing["required_roles"]=required
        result["review_route"]=routing
    return result


def decorate_execution(store, record):
    data=deepcopy(record)
    rows=controls(store,record["project"],record["execution_batch_id"])
    if rows:data["seeded_control_results"]=rows
    return data


def pending_review(store, record, clause, reference, resolves=None, exemptions=None):
    human=clause.get("human_reviewer") or {}
    support={"review":{"role":human.get("role"),"captures_confidence":human.get("captures_confidence",False),
        "timeout":clause.get("review_timeout") or "24h","on_timeout":clause.get("on_timeout","block"),"escalate_to":clause.get("escalate_to")},
        "criteria":clause["criteria"],"evidence":{"conversation":record["conversation"],"artifacts":record["artifacts"]}}
    oracle=canonical({"type":"human_reviewer","role":human.get("role","review"),"version":"1"})
    blocked=blocked_result(store,record,clause,reference,"human_reviewer",oracle,persist=False)
    result=blocked or result_base(record,reference,"human_reviewer",oracle,support)
    if not blocked:result["disposition"]="awaiting_review"
    if resolves:result["resolves"]=resolves
    if exemptions:result["supporting_evidence"]["requalified_controls"]=exemptions
    return store.append_result(record["project"],result)


async def assess_expectation(engine, record, clause, reference, resolves=None, exemptions=None, previous_members=None):
    store=engine.storage
    if clause.get("human_reviewer"):
        return pending_review(store,record,clause,reference,resolves,exemptions)
    if clause.get("judge"):
        oracle=judge_identity(clause)
        result=None if exemptions else blocked_result(store,record,clause,reference,"judge",oracle,persist=False)
        result=result or await engine.judge(record,clause,reference,persist=False)
        if resolves:result["resolves"]=resolves
        if exemptions:result["supporting_evidence"]["requalified_controls"]=exemptions
        return store.append_result(record["project"],result)
    panel=clause["multi_judge"]
    configured=panel["judges"] if panel["purpose"]=="independence" else [panel["judge"]]*panel["samples"]
    members=[];excluded=[]
    for index,config in enumerate(configured):
        member_clause={**clause,"judge":config,"multi_judge":None}
        oracle=judge_identity(member_clause)
        previous=(previous_members or [])[index] if index<len(previous_members or []) else None
        seen=(previous or {}).get("supporting_evidence",{}).get("provider_response",{})
        preserve=previous is not None and previous["oracle"]==oracle and (previous["verdict"] is not None or isinstance(seen,dict) and seen.get("verdict") in ("pass","fail"))
        child=deepcopy(previous) if preserve else blocked_result(store,record,member_clause,reference,"judge",oracle,persist=False)
        if child is not None:
            if not preserve:excluded.append(oracle)
        else:
            wire_clause=deepcopy(member_clause)
            if config["confidence_source"]=="agreement":wire_clause["judge"]["confidence_source"]="self_rating"
            child=await engine.judge(record,wire_clause,reference,persist=False)
            child["oracle"]=oracle
        members.append(child)
        if not preserve:store.save_decision("member_result",record["project"],child)
    count=len(configured)
    consensus=panel["consensus"]
    eligible=count-len(excluded)
    quorum=consensus.get("min_qualified") or count
    voters=[r for r in members if r["verdict"] is not None]
    support={"purpose":panel["purpose"],"member_results":members,"excluded_oracles":excluded,
             "quorum":quorum,"configuration":deepcopy(panel),"agreement":"not_computed"}
    result=result_base(record,reference,"judge",panel_identity(clause),support)
    result["panel"]={"configured":count,"counted":len(voters)}
    disagreement=False
    if eligible<quorum:result["disposition"]="not_assessed"
    elif len(voters)<eligible:pass  # unavailable member, no implicit vote
    else:
        passes=sum(r["verdict"]=="pass" for r in voters)
        fails=len(voters)-passes
        if consensus["method"]=="voting":
            threshold=consensus.get("threshold") or "majority"
            needed=len(voters)//2+1 if threshold=="majority" else len(voters) if threshold=="unanimous" else math.ceil(threshold*len(voters))
            verdict="pass" if passes>=needed else "fail" if fails>=needed else None
            confidence=min((r["confidence"] for r in voters if r["verdict"]==verdict),default=0)
        else:
            total=sum(r["confidence"] for r in voters)
            score=sum(r["confidence"] for r in voters if r["verdict"]=="pass")/total if total else .5
            verdict="pass" if score>.5 else "fail" if score<.5 else None
            confidence=total/len(voters) if voters else 0
            support["weighted_pass_score"]=score
        agreement=(passes if verdict=="pass" else fails)/len(voters) if verdict else max(passes,fails)/len(voters)
        support["agreement"]=agreement
        if verdict is None or agreement<(consensus.get("min_agreement") or 0):
            if consensus.get("on_disagreement","human_review")=="fail":
                verdict="fail"
                confidence=min((r["confidence"] for r in voters),default=0)
            else:disagreement=True
        if disagreement:result["disposition"]="awaiting_review"
        else:
            result.update(verdict=verdict,confidence=confidence,
                          disposition="actionable" if confidence>=clause["confidence_threshold"] else "inconclusive")
        assertions=max((r.get("assertions",1) for r in voters),default=1)
        if assertions>1:result["assertions"]=assertions
    if resolves:result["resolves"]=resolves
    if exemptions:support["requalified_controls"]=exemptions
    result=store.append_result(record["project"],result)
    if disagreement:pending_review(store,record,clause,reference,result["id"])
    return result


class ControlManager:
    def __init__(self, store):self.store=store

    def halted(self, project, batch):
        return any(c["invalidation_scope"]=="full_run" and c["reason"]=="halt_run" for c in controls(self.store,project,batch))

    def record(self, records):
        record=records[0];config=record["configuration"]["scenario"]["seeded_control"]
        assessments=[];roots=[];confirmed=True;confirmation_details=[]
        for r in records:
            if r["status"]!="completed":confirmed=False
            for row in self.store.list_results(r["project"],r["id"]):
                from engine.decision import find_clause
                classes=clause_classes(find_clause(r,row["clause"]))
                if classes is not None and config["defect_class"] not in classes:continue
                roots.append(row["id"])
                assessments.append(row["id"])
                assessments.extend(m["id"] for m in row["supporting_evidence"].get("member_results",[]))
            if config["confirmed_by"]=="human_reviewer":confirmed=False
            elif config["confirmed_by"]=="validator" and r["status"]=="completed":
                from engine.assessment import AssessmentEngine
                check=AssessmentEngine(self.store,None).validate(r,config["confirmation"],"confirmation",persist=False)
                confirmed=confirmed and check["verdict"]=="pass"
                confirmation_details.append(check)
        class_config=next((c for c in record["configuration"].get("defect_classes",[]) if c["name"]==config["defect_class"]),{})
        prior=config.get("difficulty_prior")
        if prior is None:prior=class_config.get("difficulty_prior")
        prior="not_established" if prior is None else prior
        source=config.get("prior_source") or class_config.get("prior_source")
        data={"id":control_key(record),"execution_batch_id":record["execution_batch_id"],"suite":record["suite"],
              "scenario":record["scenario"],"defect_class":config["defect_class"],"kind":config["kind"],
              "confirmed_by":config["confirmed_by"],"confirmed":confirmed,"assessments":assessments,
              "root_assessments":roots,
              "confirmation_details":confirmation_details,"policy":record["configuration"]["execution"].get("on_seeded_control_miss","skip_class"),
              "needs_reference_review":config["kind"]=="defect" and prior==0 and source=="reference_oracles","source_execution":record["configuration"]["scenario"]["evidence"].get("source_execution") if record["configuration"]["scenario"]["evidence"] else None}
        from engine.decision import digest
        data["recorded_at"]=timestamp()
        data["evidence_fingerprint"]=digest([r["conversation"] for r in records])
        if config["kind"]=="defect":data["difficulty_prior"]=prior
        self.store.save_decision("control",record["project"],data)

    def ensure_unrun(self, records):
        groups={}
        for r in records:
            if r["configuration"]["scenario"]["seeded_control"] is not None:groups.setdefault(control_key(r),[]).append(r)
        for key,group in groups.items():
            if self.store.decision_record("control",group[0]["project"],key) is None:self.record(group)
