"""Project models and schemas.

References:
- Volume II — Domain Model
- Appendix A §A.1
- Appendix B §B.2, §B.3
"""

from typing import List, Optional, Union
from pydantic import Field, model_validator
from engine.models.base import AQEFBaseModel, JSONNumber, JSONInteger
from engine.models.contract import Contract, JudgeConfig
from engine.models.dataset import Dataset
from engine.models.environment import Environment
from engine.models.execution_config import ExecutionConfig
from engine.models.gate import QualityGate
from engine.models.suite import Suite


class DefectClassConfig(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    difficulty_prior: Optional[Union[JSONNumber, str]] = None
    prior_basis: Optional[JSONInteger] = Field(None, ge=1)
    prior_source: Optional[str] = None
    reference_oracles: Optional[List[JudgeConfig]] = None

    @model_validator(mode="after")
    def validate_defect_class(self) -> "DefectClassConfig":
        # Appendix B §B.2 DefectClassConfig:
        # Cross-field rule: prior_basis and prior_source are REQUIRED when difficulty_prior is a number.
        # An absent difficulty_prior is equivalent to "not_established"; a schema MUST NOT default it to 0.0.
        if self.difficulty_prior is not None:
            if isinstance(self.difficulty_prior, str):
                if self.difficulty_prior != "not_established":
                    raise ValueError(f"String difficulty_prior must be 'not_established', got '{self.difficulty_prior}'")
            elif isinstance(self.difficulty_prior, (int, float)):
                if not (0.0 <= self.difficulty_prior <= 1.0):
                    raise ValueError(f"Numeric difficulty_prior must be between 0.0 and 1.0, got {self.difficulty_prior}")
                if self.prior_basis is None:
                    raise ValueError("'prior_basis' is REQUIRED when difficulty_prior is a number")
                if self.prior_source not in ("reference_oracles", "human_reviewer"):
                    raise ValueError("'prior_source' must be 'reference_oracles' or 'human_reviewer'")

        return self


class Project(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    environments: List[Environment] = Field(..., min_length=1)
    suites: List[Suite] = Field(default_factory=list)
    execution: Optional[ExecutionConfig] = None
    datasets: List[Dataset] = Field(default_factory=list)
    defect_classes: List[DefectClassConfig] = Field(default_factory=list)
    contracts: List[Union[Contract, str]] = Field(default_factory=list)
    quality_gates: List[QualityGate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_project(self) -> "Project":
        # Appendix A §A.1, Appendix B §B.2:
        # At least one Environment MUST be defined.
        if not self.environments:
            raise ValueError("A Project MUST define at least one Environment in 'environments'")

        # Environment names must be unique within Project
        seen_env_names = set()
        for env in self.environments:
            if env.name in seen_env_names:
                raise ValueError(f"Duplicate environment name '{env.name}' in Project '{self.name}'")
            seen_env_names.add(env.name)

        # Suite names must be unique within Project
        seen_suite_names = set()
        for suite in self.suites:
            if suite.name in seen_suite_names:
                raise ValueError(f"Duplicate suite name '{suite.name}' in Project '{self.name}'")
            seen_suite_names.add(suite.name)

        # Appendix B §B.3 Gate name uniqueness:
        # "A Quality Gate name MUST be unique across a Project's quality_gates and those of all its Suites."
        seen_gate_names = set()
        for g in self.quality_gates:
            if g.name in seen_gate_names:
                raise ValueError(f"Duplicate quality gate name '{g.name}' in Project '{self.name}'")
            seen_gate_names.add(g.name)

        for suite in self.suites:
            for g in suite.quality_gates:
                if g.name in seen_gate_names:
                    raise ValueError(
                        f"Quality Gate name '{g.name}' in Suite '{suite.name}' collides with an existing Gate name in Project or other Suite"
                    )
                seen_gate_names.add(g.name)

        return self
