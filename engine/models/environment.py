"""Environment models and schemas.

References:
- Volume II — Domain Model
- Volume III — Execution Engine (Action Boundary)
- Appendix A §A.2
- Appendix B §B.2, §B.3
- Implementer's Brief §3 (Scope: action_boundary not in scope)
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, StrictBool, model_validator
from engine.models.base import AQEFBaseModel


class BoundaryEntryKind(str, Enum):
    STUB = "stub"
    SANDBOX = "sandbox"
    REAL = "real"


class BoundaryEntry(AQEFBaseModel):
    target: str = Field(..., min_length=1)
    kind: BoundaryEntryKind
    tripwire: StrictBool = False

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
    name: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolConfig(AQEFBaseModel):
    tools: List[ToolDef] = Field(default_factory=list)


class Environment(AQEFBaseModel):
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
        # BRIEF.md §3 Scope:
        # "Not in scope: action_boundary: acting subjects with tools; reject a configuration that needs it"
        if self.tool_configuration is not None:
            raise ValueError(
                "Acting subjects with tools (tool_configuration / action_boundary) are not in scope for this engine"
            )

        # Appendix B §B.2 Environment:
        # action_boundary is REQUIRED when tool_configuration is not null.
        if self.tool_configuration is not None and self.action_boundary is None:
            raise ValueError("action_boundary is REQUIRED when tool_configuration is not null")

        return self
