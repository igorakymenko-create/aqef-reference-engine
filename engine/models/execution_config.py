"""Execution configuration models.

References:
- Volume III — Execution Engine
- Appendix A §A.9
- Appendix B §B.2, §B.3
"""

from enum import Enum
from typing import Optional
from pydantic import Field, field_validator, model_serializer
from engine.models.base import AQEFBaseModel, JSONInteger


class SeededControlMissPolicy(str, Enum):
    SKIP_CLASS = "skip_class"
    HALT_RUN = "halt_run"


class RetryConfig(AQEFBaseModel):
    max_attempts: JSONInteger = Field(..., ge=1)
    on: str = Field(...)

    @field_validator("on")
    @classmethod
    def validate_on_failure(cls, v: str) -> str:
        # Appendix B §B.2 RetryConfig:
        # "the 'on' field is constrained to infrastructure_failure only.
        # A schema MUST reject any other value. Retrying after a genuine Response is strictly prohibited."
        if v != "infrastructure_failure":
            raise ValueError(f"RetryConfig.on MUST be 'infrastructure_failure', got '{v}'")
        return v


class ExecutionConfig(AQEFBaseModel):
    timeout: Optional[str] = None
    retry: Optional[RetryConfig] = None
    scheduling: Optional[str] = None
    parallelization: Optional[JSONInteger] = Field(None, ge=1)
    on_seeded_control_miss: SeededControlMissPolicy = SeededControlMissPolicy.SKIP_CLASS

    @model_serializer(mode="wrap")
    def serialize_supplied_fields(self, handler):
        # A.9 field-by-field inheritance depends on presence, including after SQLite
        # round trips. Serializing defaults would turn omitted fields into overrides.
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}
