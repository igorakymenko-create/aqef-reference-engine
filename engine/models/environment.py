"""Environment models and schemas.

References:
- Volume II — Domain Model
- Volume III — Execution Engine (Action Boundary)
- Appendix A §A.2
- Appendix B §B.2, §B.3
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from jsonschema import SchemaError
from pydantic import Field, StrictBool, field_validator, model_validator
from engine.models.base import ConfigurationModel as AQEFBaseModel
from engine.tool_boundary import IDENTIFIER, validate_parameter_schema, validate_pattern


class BoundaryEntryKind(str, Enum):
    STUB = "stub"
    SANDBOX = "sandbox"
    REAL = "real"


class BoundaryEntry(AQEFBaseModel):
    target: str = Field(..., min_length=1)
    kind: BoundaryEntryKind
    tripwire: StrictBool = False

    @field_validator("target")
    @classmethod
    def supported_target(cls, value):
        validate_pattern(value)
        return value

    @model_validator(mode="after")
    def validate_tripwire(self) -> "BoundaryEntry":
        # Appendix B §B.2:
        # Cross-field rule: tripwire: true is valid only when kind is stub.
        if self.tripwire and self.kind != BoundaryEntryKind.STUB:
            raise ValueError(f"tripwire: true is valid only when kind is 'stub', got kind='{self.kind.value}'")
        return self


class ActionBoundary(AQEFBaseModel):
    enforced: StrictBool
    entries: List[BoundaryEntry] = Field(..., min_length=1)


class ToolDef(AQEFBaseModel):
    name: str = Field(..., min_length=1, pattern=rf"^{IDENTIFIER.pattern}$")
    parameters: Dict[str, Dict[str, Any] | StrictBool]

    @field_validator("parameters")
    @classmethod
    def check_parameters(cls, value):
        for name, schema in value.items():
            try:
                validate_parameter_schema(schema)
            except (ValueError, SchemaError) as exc:
                raise ValueError(f"Invalid parameter schema for '{name}': {exc}") from exc
        return value


class ToolConfig(AQEFBaseModel):
    tools: List[ToolDef]

    @model_validator(mode="after")
    def unique_tools(self):
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Tool names must be unique")
        return self


class Environment(AQEFBaseModel):
    nullable_fields = frozenset({"tool_configuration"})  # A.2 explicitly allows null.
    name: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    prompt_version: str = Field(..., min_length=1)
    # Appendix A §A.2: tool_configuration | ToolConfig or null | MUST
    # A configuration without the key is incomplete and must be rejected; null is the Single-LLM case.
    tool_configuration: Optional[ToolConfig] = Field(...)
    action_boundary: Optional[ActionBoundary] = None
    infra_target: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_environment(self) -> "Environment":
        # Appendix B §B.2 Environment:
        # action_boundary is REQUIRED when tool_configuration is not null.
        if self.tool_configuration is not None and self.action_boundary is None:
            raise ValueError("action_boundary is REQUIRED when tool_configuration is not null")

        return self
