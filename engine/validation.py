"""Configuration load-time and semantic validation.

References:
- Appendix B §B.2, §B.3 (Cross-Type Validation Rules)
- Volume I, Chapter 3 (Independent Oracles)
- Volume II (Domain Model)
- Volume IV (Datasets and Variables)
- Volume VII (Contracts and Composition)
"""

from typing import Callable, Dict, List, Optional, Set
from engine.composition import compose_scenario_effective_contract
from engine.models.contract import Contract
from engine.models.dataset import Dataset
from engine.models.project import Project


class ConfigurationValidationError(ValueError):
    """Raised when a configuration violates an AQEF specification rule."""
    pass


def validate_dataset_references(datasets, lookup_dataset=None) -> None:
    """B.3 Dataset reference: resolve base_dataset in declarations or same-Project registry."""
    known = {f"{dataset.name}@{dataset.version}":dataset for dataset in datasets}
    for dataset in datasets:
        reference = dataset.base_dataset
        if reference is None:
            continue
        name, separator, version = reference.partition("@")
        if not separator or not name or not version:
            raise ConfigurationValidationError(f"Dataset '{dataset.name}@{dataset.version}' base_dataset must name a version (name@version)")
        resolved = known.get(reference)
        if resolved is None and lookup_dataset is not None:
            resolved = lookup_dataset(name, version)
        if resolved is None:
            raise ConfigurationValidationError(f"Dataset '{dataset.name}@{dataset.version}' base_dataset '{reference}' cannot be resolved in this Project (B.3 Dataset reference)")


def validate_contract_identity(contract, environments) -> None:
    """B.3 Independent Oracle — identity, including every member/sample configuration."""
    for expectation in contract.expectations:
        judges = [expectation.judge] if expectation.judge else (
            expectation.multi_judge.judges or [expectation.multi_judge.judge]
        ) if expectation.multi_judge else []
        for judge in judges:
            for environment in environments:
                if judge.model.strip().lower() == environment.model_version.strip().lower():
                    raise ConfigurationValidationError(
                        f"Independent Oracle violation: Judge model '{judge.model}' MUST NOT be identical "
                        f"to Environment '{environment.name}' model_version '{environment.model_version}'")


def validate_oracle_identity(project, lookup_contract=None) -> None:
    for suite in project.suites:
        for scenario in suite.scenarios:
            try:
                contract = compose_scenario_effective_contract(project.contracts, suite.contracts,
                    scenario.contract, lookup_contract)
            except (ValueError, RecursionError) as exc:
                raise ConfigurationValidationError(f"Independent Oracle identity: cannot resolve Contract for '{suite.name}/{scenario.name}': {exc}") from exc
            validate_contract_identity(contract, project.environments)


def validate_gate_coverage(project: Project, lookup_contract=None) -> None:
    """WD 0.41.3 A.10/B.3: dimension Gates need a non-control clause in scope."""
    dimensions = {"functional", "semantic", "operational", "safety"}
    if not any(g.aggregate in dimensions for g in project.quality_gates) and not any(
        g.aggregate in dimensions for suite in project.suites for g in suite.quality_gates
    ):
        return
    covered = {}
    for suite in project.suites:
        found = set()
        for scenario in suite.scenarios:
            if scenario.seeded_control is not None:
                continue
            try:
                contract = compose_scenario_effective_contract(project.contracts, suite.contracts,
                    scenario.contract, lookup_contract)
            except ValueError as exc:
                raise ConfigurationValidationError(f"Gate coverage: cannot resolve Contract for '{suite.name}/{scenario.name}': {exc}") from exc
            found.update(clause.dimension.value for clause in [*contract.constraints, *contract.expectations])
        covered[suite.name] = found
        for gate in suite.quality_gates:
            if gate.aggregate in dimensions and gate.aggregate not in found:
                raise ConfigurationValidationError(f"Quality Gate '{gate.name}' aggregate '{gate.aggregate}' has no non-Seeded-Control clause in Suite '{suite.name}' (A.10/B.3 Gate coverage)")
    all_dimensions = set().union(*covered.values()) if covered else set()
    for gate in project.quality_gates:
        if gate.aggregate in dimensions and gate.aggregate not in all_dimensions:
            raise ConfigurationValidationError(f"Quality Gate '{gate.name}' aggregate '{gate.aggregate}' has no non-Seeded-Control clause in Project '{project.name}' (A.10/B.3 Gate coverage)")


def validate_project_configuration(
    project: Project,
    lookup_reusable_contract: Optional[Callable[[str], Optional[Contract]]] = None,
    lookup_dataset: Optional[Callable[[str, str], Optional[Dataset]]] = None,
) -> None:
    """Validate a complete Project configuration against all Appendix B §B.3 rules."""
    # 1. Dataset Index: map "name@version" -> Dataset
    datasets_map: Dict[str, Dataset] = {}
    for ds in project.datasets:
        key = f"{ds.name}@{ds.version}"
        datasets_map[key] = ds

    validate_dataset_references(project.datasets, lookup_dataset)

    def _get_dataset(ref: str) -> Optional[Dataset]:
        if ref in datasets_map:
            return datasets_map[ref]
        if lookup_dataset:
            parts = ref.split("@", 1)
            if len(parts) == 2:
                return lookup_dataset(parts[0], parts[1])
        return None

    # 2. Gate name uniqueness across project and all suites
    seen_gate_names: Set[str] = set()
    for g in project.quality_gates:
        if g.name in seen_gate_names:
            raise ConfigurationValidationError(f"Quality Gate name '{g.name}' is duplicated in project quality_gates")
        seen_gate_names.add(g.name)

    for suite in project.suites:
        for g in suite.quality_gates:
            if g.name in seen_gate_names:
                raise ConfigurationValidationError(
                    f"Quality Gate name '{g.name}' in Suite '{suite.name}' collides with an existing Gate name"
                )
            seen_gate_names.add(g.name)

    # 3. Environment validations
    env_models: Set[str] = {env.model_version for env in project.environments}

    # 4. Suite and Scenario validations
    for suite in project.suites:
        for scenario in suite.scenarios:
            # Check effective contract exists and is valid
            try:
                effective_contract = compose_scenario_effective_contract(
                    project_contracts=project.contracts,
                    suite_contracts=suite.contracts,
                    scenario_contract=scenario.contract,
                    lookup_contract=lookup_reusable_contract,
                )
            except Exception as e:
                raise ConfigurationValidationError(
                    f"Invalid contract composition for Scenario '{scenario.name}' in Suite '{suite.name}': {e}"
                ) from e

            # Independent Oracle — identity (Volume I, Ch. 3; Appendix B §B.3):
            # A JudgeConfig's model MUST NOT be identical to the Environment's model_version
            validate_contract_identity(effective_contract, project.environments)

            if scenario.seeded_control:
                control=scenario.seeded_control
                class_config=next((c for c in project.defect_classes if c.name==control.defect_class),None)
                refs=control.reference_oracles or (class_config.reference_oracles if class_config else None) or []
                tested=[]
                for exp in effective_contract.expectations:
                    if exp.judge:tested.append(exp.judge.model)
                    if exp.multi_judge:
                        tested.extend(j.model for j in (exp.multi_judge.judges or [exp.multi_judge.judge]))
                if any(ref.model.strip().lower()==model.strip().lower() for ref in refs for model in tested):
                    raise ConfigurationValidationError(f"Seeded Control '{scenario.name}' reference Oracle MUST be independent of tested Oracle")

            # Dataset reference check
            if scenario.dataset:
                ds = _get_dataset(scenario.dataset)
                if not ds:
                    raise ConfigurationValidationError(
                        f"Scenario '{scenario.name}' references Dataset '{scenario.dataset}' which cannot be resolved"
                    )

                # Variable interpolation check for dataset rows
                if scenario.prompt:
                    template_vars = scenario.prompt.extract_variables()
                    if ds.rows:
                        for row in ds.rows:
                            missing = template_vars - set(row.variables.keys())
                            if missing:
                                raise ConfigurationValidationError(
                                    f"Dataset '{scenario.dataset}' row '{row.id}' lacks required variables {missing} "
                                    f"for Scenario '{scenario.name}' prompt template"
                                )

    validate_gate_coverage(project, lookup_reusable_contract)
