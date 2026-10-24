"""Quality Gate models and schemas.

References:
- Volume I, Chapter 6 — Aggregate Basis and Quality Gates
- Appendix A §A.10
- Appendix B §B.2, §B.3
"""

from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import Field, StrictBool, field_validator, model_validator
from engine.models.base import ConfigurationModel as AQEFBaseModel, JSONNumber, JSONInteger


class GateFailureAction(str, Enum):
    BLOCK_RELEASE = "block_release"
    WARN = "warn"


class MinBasis(AQEFBaseModel):
    results: Optional[JSONInteger] = Field(None, ge=1)
    scenarios: Optional[JSONInteger] = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_min_basis(self) -> "MinBasis":
        # Appendix B §B.2 MinBasis:
        # Cross-field rule: at least one of results or scenarios MUST be present.
        if self.results is None and self.scenarios is None:
            raise ValueError("MinBasis requires at least one of 'results' or 'scenarios' to be present")
        return self


class QualityGate(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    aggregate: str = Field(..., min_length=1)
    threshold: Union[JSONNumber, Dict[str, Any]]
    compare_against: Optional[str] = None
    min_basis: Optional[MinBasis] = None
    on_failure: GateFailureAction
    override_requires: Optional[str] = None
    require_admitted_judges: StrictBool = False

    @field_validator("threshold")
    @classmethod
    def numeric_threshold_map(cls, value):
        from engine.validators import number
        def check(node):
            if isinstance(node, dict):
                for child in node.values():
                    check(child)
            else:
                number(node)
        check(value)
        return value
