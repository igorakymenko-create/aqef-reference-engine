"""Contract Composition Engine.

References:
- Volume VII — Quality Contracts (§Contract Composition, §Reusable Contracts)
- Appendix A §A.5
- Appendix B §B.3 (Effective Contract, Composition conflict surfacing)
"""

from typing import Callable, Dict, List, Optional, Union
from engine.models.contract import Constraint, Contract, Expectation, Policies


class ContractCompositionConflictError(ValueError):
    """Raised for conflicting clauses, source weights, or weakening Policies."""
    pass


class InvalidEffectiveContractError(ValueError):
    """Raised when an effective contract contains zero clauses or is invalid."""
    pass


def _are_constraints_identical(c1: Constraint, c2: Constraint) -> bool:
    """Check if two constraints have identical content."""
    return (
        c1.validator == c2.validator
        and c1.target == c2.target
        and c1.expected == c2.expected
        and c1.veto == c2.veto
        and c1.dimension == c2.dimension
        and c1.defect_classes == c2.defect_classes
    )


def _are_expectations_identical(e1: Expectation, e2: Expectation) -> bool:
    """Check if two expectations have identical content."""
    return (
        e1.criteria == e2.criteria
        and e1.confidence_threshold == e2.confidence_threshold
        and e1.review_timeout == e2.review_timeout
        and e1.on_timeout == e2.on_timeout
        and e1.escalate_to == e2.escalate_to
        and e1.dimension == e2.dimension
        and e1.defect_classes == e2.defect_classes
        and (e1.judge == e2.judge)
        and (e1.multi_judge == e2.multi_judge)
        and (e1.human_reviewer == e2.human_reviewer)
    )


def resolve_contract(
    contract_or_ref: Union[Contract, str],
    lookup_contract: Optional[Callable[[str], Optional[Contract]]] = None,
) -> Contract:
    """Resolve a Contract or contract reference string to a Contract object."""
    if isinstance(contract_or_ref, Contract):
        return contract_or_ref
    if isinstance(contract_or_ref, str):
        if not lookup_contract:
            raise ValueError(f"Cannot resolve reusable contract reference '{contract_or_ref}': no lookup function provided")
        resolved = lookup_contract(contract_or_ref)
        if not resolved:
            raise ValueError(f"Referenced reusable contract '{contract_or_ref}' not found")
        return resolved
    raise ValueError(f"Expected Contract or str reference, got {type(contract_or_ref)}")


def compose_contracts(
    contracts: List[Contract],
    allow_empty: bool = False,
    levels=None,
) -> Contract:
    """Compose multiple contracts additively following AQEF Volume VII rules.

    Rules:
    - Composition is additive: all clauses apply.
    - Two contributed clauses are the same clause only when they declare the same `id`.
    - If they have identical content, they collapse to one clause.
    - If they have differing content, a ContractCompositionConflictError MUST be raised.
    - A clause without an `id` is never the same clause as another: it is added alongside.
    - The effective contract must contain at least one clause (unless allow_empty=True).
    """
    effective_constraints: List[Constraint] = []
    effective_expectations: List[Expectation] = []
    seen_constraint_ids: Dict[str, Constraint] = {}
    seen_expectation_ids: Dict[str, Expectation] = {}

    combined_policy: Optional[Policies] = None
    levels = levels if levels is not None else [(0, 0)] * len(contracts)
    contributions = [(level, c.policies.validator_composition) for c, level in zip(contracts, levels) if c.policies]
    strictness = {"OR": 0, "AND": 1, "hard-veto": 2}
    for lower_level, lower_value in contributions:
        if any(higher_level < lower_level and strictness[higher_value] > strictness[lower_value]
               for higher_level, higher_value in contributions):
            raise ContractCompositionConflictError(
                f"Policy composition conflict: lower validator_composition '{lower_value}' weakens a higher contribution")
    if contributions:
        combined_policy = Policies(validator_composition=max((v for _, v in contributions), key=strictness.get))
    weights = {"constraints": [], "expectations": []}
    seen_weights = {}

    for contract in contracts:
        weight = contract.policies.weight if contract.policies and contract.policies.weight is not None else 1.0
        for clause in [*contract.constraints, *contract.expectations]:
            if clause.id:
                if clause.id in seen_weights and seen_weights[clause.id] != weight:
                    raise ContractCompositionConflictError(f"Composition conflict on clause id '{clause.id}': differing weight")
                seen_weights[clause.id] = weight

        # Constraints
        for c in contract.constraints:
            if c.id is not None:
                if c.id in seen_constraint_ids:
                    existing = seen_constraint_ids[c.id]
                    if not _are_constraints_identical(existing, c):
                        raise ContractCompositionConflictError(
                            f"Composition conflict on constraint clause id '{c.id}': differing content detected. "
                            f"Existing: {existing.model_dump()}, Contributed: {c.model_dump()}"
                        )
                    # Identical: collapse into one, do not duplicate
                    continue
                if c.id in seen_expectation_ids:
                    raise ContractCompositionConflictError(
                        f"Composition conflict: clause id '{c.id}' is used as both a constraint and an expectation"
                    )
                seen_constraint_ids[c.id] = c
                effective_constraints.append(c)
                weights["constraints"].append(weight)
            else:
                # No ID: always added
                effective_constraints.append(c)
                weights["constraints"].append(weight)

        # Expectations
        for e in contract.expectations:
            if e.id is not None:
                if e.id in seen_expectation_ids:
                    existing = seen_expectation_ids[e.id]
                    if not _are_expectations_identical(existing, e):
                        raise ContractCompositionConflictError(
                            f"Composition conflict on expectation clause id '{e.id}': differing content detected. "
                            f"Existing: {existing.model_dump()}, Contributed: {e.model_dump()}"
                        )
                    # Identical: collapse into one, do not duplicate
                    continue
                if e.id in seen_constraint_ids:
                    raise ContractCompositionConflictError(
                        f"Composition conflict: clause id '{e.id}' is used as both an expectation and a constraint"
                    )
                seen_expectation_ids[e.id] = e
                effective_expectations.append(e)
                weights["expectations"].append(weight)
            else:
                # No ID: always added
                effective_expectations.append(e)
                weights["expectations"].append(weight)

    if not allow_empty and not effective_constraints and not effective_expectations:
        raise InvalidEffectiveContractError("Effective composed contract has zero clauses; at least one clause is required")

    if (combined_policy and any(c.policies and c.policies.weight is not None for c in contracts)
            and len(set(weights["constraints"] + weights["expectations"])) == 1):
        combined_policy.weight = (weights["constraints"] + weights["expectations"])[0]
    result = Contract.model_construct(
        name="effective_contract",
        constraints=effective_constraints,
        expectations=effective_expectations,
        policies=combined_policy,
        extends=[],
    )
    result._clause_weights = weights
    return result


def effective_contract_data(contract):
    """Frozen runtime Contract, with aligned source-weight arrays (VII/A.5/B.3)."""
    return {**contract.model_dump(mode="json", context={"include_absent":True}), "clause_weights":contract._clause_weights}


def compose_scenario_effective_contract(
    project_contracts: List[Union[Contract, str]],
    suite_contracts: List[Union[Contract, str]],
    scenario_contract: Optional[Union[Contract, str]],
    lookup_contract: Optional[Callable[[str], Optional[Contract]]] = None,
) -> Contract:
    """Compose the effective contract for a Scenario run within a Suite and Project.

    Level hierarchy:
    Project -> Suite -> Scenario
    A lower level adds clauses but cannot remove or weaken a higher level's clause.
    """
    contributing: List[Contract] = []
    levels = []

    # Helper to resolve `extends` within a contract recursively
    def _resolve_with_extends(c: Contract, level, depth=0, visiting=()) -> List[Contract]:
        identity = c.name or id(c)
        if identity in visiting:
            raise ContractCompositionConflictError("Contract extends cycle")
        res: List[Contract] = []
        for ext in c.extends:
            ext_c = resolve_contract(ext, lookup_contract)
            res.extend(_resolve_with_extends(ext_c, level, depth + 1, (*visiting, identity)))
        res.append(c)
        levels.append((level, -depth))
        return res

    for pc in project_contracts:
        resolved = resolve_contract(pc, lookup_contract)
        contributing.extend(_resolve_with_extends(resolved, 0))

    for sc in suite_contracts:
        resolved = resolve_contract(sc, lookup_contract)
        contributing.extend(_resolve_with_extends(resolved, 1))

    if scenario_contract is not None:
        resolved = resolve_contract(scenario_contract, lookup_contract)
        contributing.extend(_resolve_with_extends(resolved, 2))

    if not contributing:
        raise InvalidEffectiveContractError(
            "No contracts supplied at Project, Suite, or Scenario level. An effective Contract with no clauses is invalid."
        )

    return compose_contracts(contributing, allow_empty=False, levels=levels)
