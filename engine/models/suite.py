"""Suite models and schemas.

References:
- Volume II — Domain Model
- Appendix A §A.3
- Appendix B §B.2, §B.3
"""

from typing import List, Optional, Union
from pydantic import Field, model_validator
from engine.models.base import ConfigurationModel as AQEFBaseModel
from engine.models.contract import Contract
from engine.models.execution_config import ExecutionConfig
from engine.models.gate import QualityGate
from engine.models.scenario import Scenario


class Suite(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    scenarios: List[Scenario] = Field(..., min_length=1)
    contracts: List[Union[Contract, str]] = Field(default_factory=list)
    quality_gates: List[QualityGate] = Field(default_factory=list)
    execution: Optional[ExecutionConfig] = None

    @model_validator(mode="after")
    def validate_suite(self) -> "Suite":
        # Appendix A §A.3, Appendix B §B.2:
        # At least one Scenario MUST be present.
        if not self.scenarios:
            raise ValueError("A Suite MUST contain at least one Scenario")

        # Scenario names MUST be unique within the Suite
        seen_scenarios = set()
        for sc in self.scenarios:
            if sc.name in seen_scenarios:
                raise ValueError(f"Duplicate scenario name '{sc.name}' within Suite '{self.name}'")
            seen_scenarios.add(sc.name)

        # Gate names within Suite MUST be unique
        seen_gates = set()
        for g in self.quality_gates:
            if g.name in seen_gates:
                raise ValueError(f"Duplicate quality gate name '{g.name}' within Suite '{self.name}'")
            seen_gates.add(g.name)

        return self
