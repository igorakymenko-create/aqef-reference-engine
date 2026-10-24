"""Tests for Quality Contracts and Contract Composition.

Section references:
- Volume VII — Quality Contracts (§Contract Language, §Constraints, §Expectations, §Confidence, §Contract Composition)
- Appendix A §A.5 (Quality Contract)
- Appendix B §B.2, §B.3 (Cross-Type Validation Rules: Effective Contract, Composition conflict surfacing)
"""

import pytest
from pydantic import ValidationError
from engine.composition import (
    ContractCompositionConflictError,
    InvalidEffectiveContractError,
    compose_contracts,
    compose_scenario_effective_contract,
)
from engine.models.contract import (
    ConfidenceSource,
    Constraint,
    Contract,
    Expectation,
    JudgeConfig,
    QualityDimension,
    TimeoutAction,
)


def test_contract_cannot_be_empty():
    # Appendix A §A.5, Appendix B §B.2:
    # "A Contract MUST contain at least one Constraint or Expectation. An empty Contract is not a valid Contract."
    with pytest.raises(ValidationError) as exc:
        Contract(name="empty_contract", constraints=[], expectations=[])
    assert "A Contract MUST contain at least one Constraint or Expectation" in str(exc.value)


def test_expectation_oracle_exclusivity():
    # Appendix B §B.2 Expectation:
    # "Exactly one of judge, multi_judge, or human_reviewer MUST be present."
    with pytest.raises(ValidationError) as exc:
        Expectation(criteria="Helpful response")  # No oracle specified
    assert "MUST specify exactly one" in str(exc.value)


def test_expectation_confidence_threshold_required_for_judge():
    # Appendix B §B.2 Expectation:
    # "confidence_threshold is REQUIRED when judge or multi_judge is present."
    with pytest.raises(ValidationError) as exc:
        Expectation(
            criteria="Helpful response",
            judge=JudgeConfig(model="claude-3-5-sonnet", confidence_source=ConfidenceSource.SELF_RATING),
        )
    assert "confidence_threshold is REQUIRED" in str(exc.value)


def test_expectation_escalate_to_required_only_on_escalate():
    # Appendix B §B.2 Expectation:
    # "escalate_to is REQUIRED when on_timeout is escalate and MUST NOT appear otherwise."
    judge = JudgeConfig(model="claude-3-5-sonnet", confidence_source=ConfidenceSource.SELF_RATING)

    # Missing escalate_to when on_timeout=escalate
    with pytest.raises(ValidationError) as exc:
        Expectation(
            criteria="Helpful response",
            judge=judge,
            confidence_threshold=0.8,
            on_timeout=TimeoutAction.ESCALATE,
        )
    assert "'escalate_to' is REQUIRED" in str(exc.value)

    # escalate_to present when on_timeout=block
    with pytest.raises(ValidationError) as exc:
        Expectation(
            criteria="Helpful response",
            judge=judge,
            confidence_threshold=0.8,
            on_timeout=TimeoutAction.BLOCK,
            escalate_to="lead_qa",
        )
    assert "'escalate_to' MUST NOT appear" in str(exc.value)


def test_custom_validator_requires_dimension():
    # Appendix B §B.3:
    # "A Constraint bound to a Custom Validator MUST declare dimension."
    with pytest.raises(ValidationError) as exc:
        Constraint(validator="my_custom_checker", target="response", expected={})
    assert "MUST declare 'dimension' explicitly" in str(exc.value)

    # Specifying dimension succeeds
    c = Constraint(
        validator="my_custom_checker",
        target="response",
        expected={},
        dimension=QualityDimension.OPERATIONAL,
    )
    assert c.dimension == QualityDimension.OPERATIONAL


def test_clause_id_unique_within_contract():
    # Appendix B §B.3 Clause identity:
    # "A clause id MUST be unique within the Contract that declares it."
    c1 = Constraint(id="c1", validator="schema", target="response", expected={})
    c2 = Constraint(id="c1", validator="latency", target="response", expected=500)
    with pytest.raises(ValidationError) as exc:
        Contract(name="contract_duplicate_ids", constraints=[c1, c2])
    assert "Duplicate clause id 'c1'" in str(exc.value)


def test_contract_composition_additive():
    # Volume VII — Contract Composition:
    # "Composition is additive by default — every contributing Contract's Constraints and Expectations apply."
    # "Two contributed clauses are the same clause only when they declare the same id. With identical content they are one clause."
    c1 = Constraint(id="schema_check", validator="schema", target="response", expected={"type": "json"})
    c2 = Constraint(id="latency_check", validator="latency", target="response", expected={"max_ms": 500})
    # Same id, identical content
    c1_dup = Constraint(id="schema_check", validator="schema", target="response", expected={"type": "json"})

    contract_a = Contract(name="ca", constraints=[c1])
    contract_b = Contract(name="cb", constraints=[c1_dup, c2])

    composed = compose_contracts([contract_a, contract_b])
    # Total constraints should be 2, because c1 and c1_dup collapse
    assert len(composed.constraints) == 2
    assert {c.id for c in composed.constraints} == {"schema_check", "latency_check"}


def test_contract_composition_surfaces_conflict():
    # Volume VII — Contract Composition; Appendix B §B.3:
    # "Where two contributing Contracts specify genuinely conflicting values for the same clause...
    # Composition MUST surface the conflict explicitly rather than silently resolve it."
    judge = JudgeConfig(model="claude-3-5-sonnet", confidence_source=ConfidenceSource.SELF_RATING)

    exp_high = Expectation(id="tone_check", criteria="Polite tone", judge=judge, confidence_threshold=0.85)
    exp_low = Expectation(id="tone_check", criteria="Polite tone", judge=judge, confidence_threshold=0.70)

    contract_high = Contract(name="ch", expectations=[exp_high])
    contract_low = Contract(name="cl", expectations=[exp_low])

    with pytest.raises(ContractCompositionConflictError) as exc:
        compose_contracts([contract_high, contract_low])
    assert "Composition conflict on expectation clause id 'tone_check'" in str(exc.value)


def test_effective_contract_must_contain_at_least_one_clause():
    # Volume VII — Contract Composition; Appendix B §B.3:
    # "For every Scenario in every Suite, the composition of the Project's contracts, the Suite's contracts,
    # and the Scenario's contract MUST contain at least one clause."
    with pytest.raises(InvalidEffectiveContractError) as exc:
        compose_scenario_effective_contract(
            project_contracts=[],
            suite_contracts=[],
            scenario_contract=None,
        )
    assert "An effective Contract with no clauses is invalid" in str(exc.value)

