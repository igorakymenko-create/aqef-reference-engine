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
            for exp in effective_contract.expectations:
                judge_models: List[str] = []
                if exp.judge:
                    judge_models.append(exp.judge.model)
                if exp.multi_judge:
                    if exp.multi_judge.judges:
                        judge_models.extend(j.model for j in exp.multi_judge.judges)
                    if exp.multi_judge.judge:
                        judge_models.append(exp.multi_judge.judge.model)

                for j_model in judge_models:
                    for env in project.environments:
                        if j_model.strip().lower() == env.model_version.strip().lower():
                            raise ConfigurationValidationError(
                                f"Independent Oracle violation: Judge model '{j_model}' MUST NOT be identical "
                                f"to Environment '{env.name}' model_version '{env.model_version}'"
                            )

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
