"""Tests for Domain Models and Appendix B Validation Rules.

Section references:
- Volume I, Chapter 3 (Independent Oracles)
- Volume II — Domain Model
- Volume III — Execution Engine (RetryConfig, ActionBoundary)
- Volume IV — Dataset Engine (§Static, §Versioning)
- Volume VIII — Test Design (Seeded Controls)
- Appendix A §A.1–§A.4, §A.8–§A.10
- Appendix B §B.2, §B.3
"""

import pytest
from pydantic import ValidationError
from engine.models.contract import (
    ConfidenceSource,
    Constraint,
    Contract,
    Expectation,
    JudgeConfig,
)
from engine.models.dataset import Dataset, DatasetSource, Row
from engine.models.environment import (
    BoundaryEntry,
    BoundaryEntryKind,
    Environment,
    ToolConfig,
    ToolDef,
)
from engine.models.execution_config import ExecutionConfig, RetryConfig
from engine.models.gate import MinBasis, QualityGate
from engine.models.project import Project
from engine.models.scenario import (
    FixedEvidence,
    PromptDef,
    Scenario,
    SeededControlConfig,
    SeededControlConfirmation,
    SeededControlKind,
)
from engine.models.suite import Suite
from engine.storage import Storage, StorageConflictError
from engine.validation import ConfigurationValidationError, validate_project_configuration


def test_project_requires_environments():
    # Appendix A §A.1, Appendix B §B.2:
    # "At least one Environment MUST be defined."
    with pytest.raises(ValidationError) as exc:
        Project(name="empty_proj", environments=[])
    assert "at least 1 item" in str(exc.value) or "at least one Environment" in str(exc.value)


def test_environment_acting_subject_rejected_per_brief_scope():
    # Implementer's Brief §3 Scope; Appendix A §A.2:
    # "action_boundary: acting subjects with tools; reject a configuration that needs it"
    tool_conf = ToolConfig(tools=[ToolDef(name="calculator", parameters={})])
    with pytest.raises(ValidationError) as exc:
        Environment(
            name="env1",
            model_version="gpt-4o",
            prompt_version="v1",
            tool_configuration=tool_conf,
            infra_target="us-east-1",
        )
    assert "Acting subjects with tools" in str(exc.value)


def test_boundary_tripwire_stub_only():
    # Appendix B §B.2 BoundaryEntry:
    # "Cross-field rule: tripwire: true is valid only when kind is stub."
    with pytest.raises(ValidationError) as exc:
        BoundaryEntry(target="api.stripe.com", kind=BoundaryEntryKind.REAL, tripwire=True)
    assert "tripwire: true is valid only when kind is 'stub'" in str(exc.value)

    # Valid when kind is stub
    entry = BoundaryEntry(target="admin.internal", kind=BoundaryEntryKind.STUB, tripwire=True)
    assert entry.tripwire is True


def test_dataset_versioning_and_immutability():
    # Volume IV — Dataset Engine (§Versioning); Appendix B §B.3:
    # "Every Dataset, regardless of source, MUST be versioned."
    # "Two configurations referencing the same Dataset name + version MUST resolve to identical rows."
    storage = Storage(db_path=":memory:")
    env = Environment(name="dev", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="local")
    proj = Project(name="p1", environments=[env])
    storage.create_project(proj)

    ds1 = Dataset(
        name="user_queries",
        version="1.0.0",
        source=DatasetSource.STATIC,
        rows=[Row(id="r1", variables={"query": "hello"})],
    )
    storage.create_dataset("p1", ds1)

    # Attempting to recreate same name@version must be rejected
    with pytest.raises(StorageConflictError) as exc:
        storage.create_dataset("p1", ds1)
    assert "already exists and is immutable" in str(exc.value)


def test_scenario_dataset_and_variables_mutually_exclusive():
    # Appendix A §A.4, Appendix B §B.2:
    # "A Scenario MUST specify either dataset or variables (or neither)... It MUST NOT specify both."
    with pytest.raises(ValidationError) as exc:
        Scenario(
            name="sc1",
            prompt=PromptDef(template="Test {{query}}"),
            dataset="queries@1.0.0",
            variables={"query": "static value"},
        )
    assert "MUST NOT specify both 'dataset' and 'variables'" in str(exc.value)


def test_scenario_prompt_variable_completeness():
    # Appendix A §A.4, Appendix B §B.3:
    # "A template referencing a Variable that is not supplied MUST be rejected before the Execution starts."
    with pytest.raises(ValidationError) as exc:
        Scenario(
            name="sc2",
            prompt=PromptDef(template="Hello {{user}}, your balance is {{balance}}"),
            variables={"user": "Alice"},  # missing balance
        )
    assert "references variables not supplied" in str(exc.value)


def test_seeded_control_clean_rules():
    # Appendix A §A.4, Appendix B §B.2 SeededControlConfig:
    # "planted_defect MUST NOT appear when kind is clean."
    # "difficulty_prior MUST NOT appear when kind is clean."
    with pytest.raises(ValidationError) as exc:
        SeededControlConfig(
            kind=SeededControlKind.CLEAN,
            defect_class="toxicity",
            planted_defect="bad word inserted",
            confirmed_by=SeededControlConfirmation.HUMAN_REVIEWER,
        )
    assert "planted_defect MUST NOT appear on a clean control" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        SeededControlConfig(
            kind=SeededControlKind.CLEAN,
            defect_class="toxicity",
            difficulty_prior=0.5,
            confirmed_by=SeededControlConfirmation.HUMAN_REVIEWER,
        )
    assert "difficulty_prior MUST NOT appear on a clean control" in str(exc.value)


def test_fixed_evidence_construction_only():
    # Appendix A §A.4, Appendix B §B.2, §B.3:
    # "Fixed Evidence MAY appear only on a Scenario whose seeded_control.confirmed_by is construction.
    # Excludes prompt, dataset, and variables."
    with pytest.raises(ValidationError) as exc:
        Scenario(
            name="sc_evidence_invalid",
            prompt=PromptDef(template="Hello"),
            evidence=FixedEvidence(conversation={"turns": [{"prompt":"hi","response":"hello"}]}),
        )
    assert "'evidence' MAY appear only on a Seeded Control whose confirmed_by is 'construction'" in str(exc.value)

    # Valid construction seeded control with fixed evidence
    control = SeededControlConfig(
        kind=SeededControlKind.DEFECT,
        defect_class="toxicity",
        planted_defect="toxic phrase",
        confirmed_by=SeededControlConfirmation.CONSTRUCTION,
    )
    sc = Scenario(
        name="sc_evidence_valid",
        seeded_control=control,
        evidence=FixedEvidence(conversation={"turns": [{"prompt":"hi","response":"hello"}]}),
    )
    assert sc.evidence is not None


def test_gate_min_basis_rules():
    # Appendix A §A.10, Appendix B §B.2 MinBasis:
    # "At least one of the two MUST be present."
    with pytest.raises(ValidationError) as exc:
        MinBasis()
    assert "requires at least one of 'results' or 'scenarios'" in str(exc.value)


def test_retry_config_only_infrastructure_failure():
    # Appendix A §A.9, Appendix B §B.2 RetryConfig:
    # "RetryConfig.on MUST be 'infrastructure_failure'... Retrying after a genuine Response is strictly prohibited."
    with pytest.raises(ValidationError) as exc:
        RetryConfig(max_attempts=3, on="validation_failure")
    assert "RetryConfig.on MUST be 'infrastructure_failure'" in str(exc.value)


def test_gate_name_uniqueness_across_project_and_suites():
    # Appendix B §B.3:
    # "A Quality Gate name MUST be unique across a Project's quality_gates and those of all its Suites."
    g1 = QualityGate(name="safety_gate", aggregate="safety", threshold=1.0, on_failure="block_release")
    g2 = QualityGate(name="safety_gate", aggregate="safety", threshold=0.9, on_failure="block_release")

    env = Environment(name="e1", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="us-east-1")
    sc = Scenario(name="sc", prompt=PromptDef(template="Hi"), contract=Contract(constraints=[Constraint(validator="schema", target="response", expected={})]))
    suite = Suite(name="s1", scenarios=[sc], quality_gates=[g2])

    with pytest.raises(ValidationError) as exc:
        Project(name="p1", environments=[env], quality_gates=[g1], suites=[suite])
    assert "collides with an existing Gate name" in str(exc.value)


def test_independent_oracle_identity_violation():
    # Volume I, Chapter 3; Appendix B §B.3:
    # "A JudgeConfig's model MUST NOT be identical to the Environment's model_version."
    judge = JudgeConfig(model="gpt-4o-2025-06-01", confidence_source=ConfidenceSource.SELF_RATING)
    contract = Contract(
        name="c1",
        expectations=[Expectation(criteria="Correct", judge=judge, confidence_threshold=0.8)],
    )

    env = Environment(
        name="prod",
        model_version="gpt-4o-2025-06-01",  # IDENTICAL to judge model!
        prompt_version="v1",
        tool_configuration=None,
        infra_target="prod",
    )
    sc = Scenario(name="sc", prompt=PromptDef(template="Hi"), contract=contract)
    suite = Suite(name="s1", scenarios=[sc])
    proj = Project(name="p1", environments=[env], suites=[suite])

    with pytest.raises(ConfigurationValidationError) as exc:
        validate_project_configuration(proj)
    assert "Independent Oracle violation" in str(exc.value)


def test_environment_name_uniqueness_within_project():
    # Appendix A §A.2, Appendix B §B.2:
    # "Environment name MUST be unique within the Project."
    e1 = Environment(name="staging", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="us-east-1")
    e2 = Environment(name="staging", model_version="claude-3-5", prompt_version="v1", tool_configuration=None, infra_target="us-west-2")
    with pytest.raises(ValidationError) as exc:
        Project(name="p1", environments=[e1, e2])
    assert "Duplicate environment name 'staging'" in str(exc.value)


def test_suite_name_uniqueness_within_project():
    # Appendix A §A.3, Appendix B §B.2:
    # "Suite name MUST be unique within the Project."
    env = Environment(name="staging", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="us-east-1")
    sc1 = Scenario(name="sc1", prompt=PromptDef(template="test"), contract=Contract(constraints=[Constraint(validator="schema", target="response", expected={})]))
    s1 = Suite(name="regression", scenarios=[sc1])
    s2 = Suite(name="regression", scenarios=[sc1])
    with pytest.raises(ValidationError) as exc:
        Project(name="p1", environments=[env], suites=[s1, s2])
    assert "Duplicate suite name 'regression'" in str(exc.value)


def test_scenario_name_uniqueness_within_suite():
    # Appendix A §A.4, Appendix B §B.2:
    # "Scenario name MUST be unique within the Suite."
    sc1 = Scenario(name="test_login", prompt=PromptDef(template="test"), contract=Contract(constraints=[Constraint(validator="schema", target="response", expected={})]))
    sc2 = Scenario(name="test_login", prompt=PromptDef(template="test"), contract=Contract(constraints=[Constraint(validator="schema", target="response", expected={})]))
    with pytest.raises(ValidationError) as exc:
        Suite(name="auth_suite", scenarios=[sc1, sc2])
    assert "Duplicate scenario name 'test_login'" in str(exc.value)


def test_multijudge_config_purpose_cross_fields():
    # Appendix B §B.2 MultiJudgeConfig:
    # When purpose is independence: judges REQUIRED (min 2), judge/samples MUST NOT appear.
    # When purpose is stability: judge and samples REQUIRED, judges MUST NOT appear.
    from engine.models.contract import ConsensusConfig, MultiJudgeConfig, MultiJudgePurpose

    j1 = JudgeConfig(model="m1", confidence_source=ConfidenceSource.SELF_RATING)
    j2 = JudgeConfig(model="m2", confidence_source=ConfidenceSource.SELF_RATING)
    consensus = ConsensusConfig(method="voting")

    # Independence with fewer than 2 judges
    with pytest.raises(ValidationError) as exc:
        MultiJudgeConfig(purpose=MultiJudgePurpose.INDEPENDENCE, judges=[j1], consensus=consensus)
    assert "at least 2 judges" in str(exc.value)

    # Stability missing samples
    with pytest.raises(ValidationError) as exc:
        MultiJudgeConfig(purpose=MultiJudgePurpose.STABILITY, judge=j1, consensus=consensus)
    assert "'judge' and 'samples' are REQUIRED" in str(exc.value)


def test_referential_integrity_environment_deletion_with_baseline():
    # Appendix C §C.8:
    # "DELETE on an Environment, Dataset, or Contract still referenced by a Baseline... MUST be rejected"
    storage = Storage(db_path=":memory:")
    env = Environment(name="prod", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="cloud")
    proj = Project(name="proj_test", environments=[env])
    storage.create_project(proj)

    # Simulate a baseline referencing environment "prod"
    with storage._get_connection() as conn:
        conn.execute(
            "INSERT INTO baselines (id, project_name, environment_name) VALUES ('b1', 'proj_test', 'prod')"
        )

    with pytest.raises(StorageConflictError) as exc:
        storage.delete_environment("proj_test", "prod")
    assert "still referenced by an existing Baseline" in str(exc.value)


def test_deletion_last_scenario_in_suite_rejected():
    # Appendix A §A.3:
    # "A Suite MUST contain at least one Scenario."
    storage = Storage(db_path=":memory:")
    sc = Scenario(name="only_scenario", prompt=PromptDef(template="hi"), contract=Contract(constraints=[Constraint(validator="schema", target="response", expected={})]))
    suite = Suite(name="single_suite", scenarios=[sc])
    env = Environment(name="e1", model_version="gpt-4o", prompt_version="v1", tool_configuration=None, infra_target="cloud")
    proj = Project(name="proj_sc", environments=[env], suites=[suite])
    storage.create_project(proj)

    with pytest.raises(StorageConflictError) as exc:
        storage.delete_scenario("proj_sc", "single_suite", "only_scenario")
    assert "Suite MUST contain at least one Scenario" in str(exc.value)

