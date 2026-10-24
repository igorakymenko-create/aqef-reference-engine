"""Scenario models and schemas.

References:
- Volume II — Domain Model
- Volume III — Execution Engine (Fixed Evidence)
- Volume VIII — Test Design (Seeded Controls)
- Appendix A §A.4
- Appendix B §B.2, §B.3
"""

import re
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import Field, model_validator
from engine.models.base import AQEFBaseModel, JSONNumber, JSONInteger
from engine.models.contract import Constraint, Contract, JudgeConfig
from engine.models.evidence import Conversation


class PromptDef(AQEFBaseModel):
    template: str = Field(..., min_length=1)

    def extract_variables(self) -> set[str]:
        # Implementation-defined placeholder syntax: {{variable_name}}
        return set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", self.template))


class SeededControlKind(str, Enum):
    DEFECT = "defect"
    CLEAN = "clean"


class SeededControlConfirmation(str, Enum):
    VALIDATOR = "validator"
    HUMAN_REVIEWER = "human_reviewer"
    CONSTRUCTION = "construction"


class SeededControlConfig(AQEFBaseModel):
    kind: SeededControlKind = SeededControlKind.DEFECT
    defect_class: str = Field(..., min_length=1)
    difficulty_prior: Optional[Union[JSONNumber, str]] = None
    planted_defect: Optional[Any] = None
    confirmed_by: SeededControlConfirmation
    confirmation: Optional[Constraint] = None
    generator: Optional[str] = None
    prior_basis: Optional[JSONInteger] = Field(None, ge=1)
    prior_source: Optional[str] = None
    reference_oracles: Optional[list[JudgeConfig]] = None

    @model_validator(mode="after")
    def validate_seeded_control(self) -> "SeededControlConfig":
        # Appendix B §B.2 SeededControlConfig:
        # Cross-field rules:
        # planted_defect is REQUIRED when kind is defect or absent, and MUST NOT appear when it is clean.
        if self.kind == SeededControlKind.DEFECT:
            if self.planted_defect is None:
                raise ValueError("planted_defect is REQUIRED when kind is 'defect'")
        elif self.kind == SeededControlKind.CLEAN:
            if self.planted_defect is not None:
                raise ValueError("planted_defect MUST NOT appear on a clean control")

        # difficulty_prior MUST NOT appear when kind is clean.
        if self.kind == SeededControlKind.CLEAN and self.difficulty_prior is not None:
            raise ValueError("difficulty_prior MUST NOT appear on a clean control")

        # difficulty_prior validation
        if self.difficulty_prior is not None:
            if isinstance(self.difficulty_prior, str):
                if self.difficulty_prior != "not_established":
                    raise ValueError(f"String difficulty_prior must be 'not_established', got '{self.difficulty_prior}'")
            elif isinstance(self.difficulty_prior, (int, float)):
                if not (0.0 <= self.difficulty_prior <= 1.0):
                    raise ValueError(f"Numeric difficulty_prior must be in [0.0, 1.0], got {self.difficulty_prior}")

        # confirmation is REQUIRED when confirmed_by is validator and MUST NOT appear otherwise.
        if self.confirmed_by == SeededControlConfirmation.VALIDATOR:
            if self.confirmation is None:
                raise ValueError("confirmation is REQUIRED when confirmed_by is 'validator'")
        else:
            if self.confirmation is not None:
                raise ValueError("confirmation MUST NOT appear unless confirmed_by is 'validator'")

        if self.kind == SeededControlKind.CLEAN and any(v is not None for v in (self.prior_basis,self.prior_source,self.reference_oracles)):
            raise ValueError("Difficulty prior provenance MUST NOT appear on clean controls")
        if isinstance(self.difficulty_prior,(int,float)):
            if self.prior_basis is None or self.prior_source not in ("reference_oracles","human_reviewer"):
                raise ValueError("Numeric control difficulty_prior requires prior_basis and prior_source")

        return self


class FixedEvidence(AQEFBaseModel):
    conversation: Conversation
    artifacts: Optional[Dict[str, Any]] = None
    source_execution: Optional[str] = Field(None, min_length=1)


class Scenario(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    contract: Optional[Union[Contract, str]] = None
    prompt: Optional[PromptDef] = None
    dataset: Optional[str] = Field(None, pattern=r"^.+@.+$")
    variables: Optional[Dict[str, Any]] = None
    seeded_control: Optional[SeededControlConfig] = None
    evidence: Optional[FixedEvidence] = None

    @model_validator(mode="after")
    def validate_scenario(self) -> "Scenario":
        # Appendix A §A.4, Appendix B §B.2:
        # A Scenario MUST specify either dataset or variables (or neither).
        # It MUST NOT specify both.
        if self.dataset is not None and self.variables is not None:
            raise ValueError("A Scenario MUST NOT specify both 'dataset' and 'variables'")

        # Appendix B §B.2, §B.3:
        # When confirmed_by is construction, the Scenario MUST carry evidence
        # and MUST NOT carry prompt, dataset, or variables.
        if self.seeded_control and self.seeded_control.confirmed_by == SeededControlConfirmation.CONSTRUCTION:
            if self.evidence is None:
                raise ValueError("Scenario with confirmed_by: construction MUST carry 'evidence'")
            if self.prompt is not None or self.dataset is not None or self.variables is not None:
                raise ValueError("Scenario with confirmed_by: construction MUST NOT carry 'prompt', 'dataset', or 'variables'")
        else:
            if self.evidence is not None:
                raise ValueError("'evidence' MAY appear only on a Seeded Control whose confirmed_by is 'construction'")

        # Prompt presence:
        # A Scenario MUST carry prompt unless its dataset is production_replay or it carries evidence.
        if self.evidence is None and self.prompt is None:
            raise ValueError("Scenario MUST carry 'prompt' unless it carries 'evidence'")

        # If fixed variables are given, all variables in prompt template must be present
        if self.variables is not None and self.prompt is not None:
            required_vars = self.prompt.extract_variables()
            missing = required_vars - set(self.variables.keys())
            if missing:
                raise ValueError(f"Prompt template references variables not supplied in Scenario.variables: {missing}")

        return self
