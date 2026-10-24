"""Quality Contract models and schemas.

References:
- Volume VII — Quality Contracts
- Volume V — Validator Engine
- Volume VI — Judge Engine
- Appendix A §A.5, §A.6, §A.7
- Appendix B §B.2, §B.3
"""

from enum import Enum
from typing import Any, List, Optional, Union
from pydantic import Field, PrivateAttr, StrictBool, model_validator
from engine.models.base import AQEFBaseModel, JSONNumber, JSONInteger


class QualityDimension(str, Enum):
    FUNCTIONAL = "functional"
    SEMANTIC = "semantic"
    OPERATIONAL = "operational"
    SAFETY = "safety"


BUILTIN_VALIDATOR_DIMENSIONS = {
    "schema": QualityDimension.FUNCTIONAL,
    "tool-call": QualityDimension.FUNCTIONAL,
    "structural": QualityDimension.FUNCTIONAL,
    "latency": QualityDimension.OPERATIONAL,
    "cost": QualityDimension.OPERATIONAL,
    "forbidden-content": QualityDimension.SAFETY,
    "boundary": QualityDimension.SAFETY,
}


class Constraint(AQEFBaseModel):
    validator: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    expected: Any = Field(...)
    veto: StrictBool = False
    id: Optional[str] = Field(None, min_length=1)
    dimension: Optional[QualityDimension] = None
    defect_classes: Optional[List[str]] = None

    @model_validator(mode="after")
    def resolve_dimension(self) -> "Constraint":
        if self.validator not in BUILTIN_VALIDATOR_DIMENSIONS and self.expected is not None and self.expected != {}:
            label = self.id or f"{self.validator} target={self.target}"
            raise ValueError(f"Clause '{label}': Custom Validator expected must be null or an empty object {{}}")
        # Appendix A §A.5, Appendix B §B.3:
        # Default by Validator type: functional for schema, tool-call, structural;
        # operational for latency, cost; safety for forbidden-content, boundary.
        # MUST be given for a Custom Validator.
        if self.dimension is None:
            if self.validator in BUILTIN_VALIDATOR_DIMENSIONS:
                self.dimension = BUILTIN_VALIDATOR_DIMENSIONS[self.validator]
            else:
                raise ValueError(
                    f"A Constraint bound to a Custom Validator ('{self.validator}') MUST declare 'dimension' explicitly"
                )
        return self


class ConfidenceSource(str, Enum):
    SELF_RATING = "self_rating"
    TOKEN_PROBABILITY = "token_probability"
    AGREEMENT = "agreement"


class JudgeConfig(AQEFBaseModel):
    model: str = Field(..., min_length=1)
    confidence_source: ConfidenceSource


class DisagreementAction(str, Enum):
    HUMAN_REVIEW = "human_review"
    FAIL = "fail"


class ConsensusConfig(AQEFBaseModel):
    method: str = Field(..., min_length=1)
    threshold: Optional[Union[str, JSONNumber]] = None
    min_agreement: Optional[JSONNumber] = Field(None, ge=0.0, le=1.0)
    on_disagreement: DisagreementAction = DisagreementAction.HUMAN_REVIEW
    min_qualified: Optional[JSONInteger] = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_threshold(self) -> "ConsensusConfig":
        # Appendix B §B.2:
        # threshold MAY appear only when method is voting; absent, it defaults to majority.
        # A numeric threshold MUST be a number, not a string: 0.75 is valid, "0.75" is not.
        if self.method == "voting":
            if self.threshold is None:
                self.threshold = "majority"
            elif isinstance(self.threshold, str):
                if self.threshold not in ("majority", "unanimous"):
                    raise ValueError(f"String threshold for voting must be 'majority' or 'unanimous', got '{self.threshold}'")
            elif isinstance(self.threshold, (int, float)):
                if not (0.5 < self.threshold <= 1.0):
                    raise ValueError(f"Numeric voting threshold must be > 0.5 and <= 1.0, got {self.threshold}")
        else:
            if self.threshold is not None:
                raise ValueError("threshold MAY appear only when method is 'voting'")
        return self


class MultiJudgePurpose(str, Enum):
    INDEPENDENCE = "independence"
    STABILITY = "stability"


class MultiJudgeConfig(AQEFBaseModel):
    purpose: MultiJudgePurpose
    judges: Optional[List[JudgeConfig]] = None
    judge: Optional[JudgeConfig] = None
    samples: Optional[JSONInteger] = Field(None, ge=2)
    consensus: ConsensusConfig

    @model_validator(mode="after")
    def validate_purpose_consistency(self) -> "MultiJudgeConfig":
        # Appendix B §B.2 MultiJudgeConfig:
        # When purpose is independence: judges REQUIRED (minItems 2), judge/samples MUST NOT appear.
        # When purpose is stability: judge and samples REQUIRED, judges MUST NOT appear.
        if self.purpose == MultiJudgePurpose.INDEPENDENCE:
            if not self.judges or len(self.judges) < 2:
                raise ValueError("When purpose is 'independence', 'judges' is REQUIRED with at least 2 judges")
            if self.judge is not None or self.samples is not None:
                raise ValueError("When purpose is 'independence', 'judge' and 'samples' MUST NOT appear")
        elif self.purpose == MultiJudgePurpose.STABILITY:
            if self.judge is None or self.samples is None:
                raise ValueError("When purpose is 'stability', 'judge' and 'samples' are REQUIRED")
            if self.judges is not None:
                raise ValueError("When purpose is 'stability', 'judges' MUST NOT appear")
        return self


class HumanReviewerConfig(AQEFBaseModel):
    role: str = Field(..., min_length=1)
    captures_confidence: StrictBool = False


class TimeoutAction(str, Enum):
    BLOCK = "block"
    ESCALATE = "escalate"


class Expectation(AQEFBaseModel):
    criteria: str = Field(..., min_length=1)
    judge: Optional[JudgeConfig] = None
    multi_judge: Optional[MultiJudgeConfig] = None
    human_reviewer: Optional[HumanReviewerConfig] = None
    confidence_threshold: Optional[JSONNumber] = Field(None, ge=0.0, le=1.0)
    review_timeout: Optional[str] = None
    on_timeout: TimeoutAction = TimeoutAction.BLOCK
    escalate_to: Optional[str] = Field(None, min_length=1)
    id: Optional[str] = Field(None, min_length=1)
    dimension: QualityDimension = QualityDimension.SEMANTIC
    defect_classes: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_expectation(self) -> "Expectation":
        # Appendix B §B.2 Expectation:
        # Exactly one of judge, multi_judge, or human_reviewer MUST be present.
        oracles = [self.judge, self.multi_judge, self.human_reviewer]
        present = [o for o in oracles if o is not None]
        if len(present) != 1:
            raise ValueError("An Expectation MUST specify exactly one of 'judge', 'multi_judge', or 'human_reviewer'")

        # confidence_threshold is REQUIRED when judge or multi_judge is present.
        # It is OPTIONAL when human_reviewer is present.
        if (self.judge is not None or self.multi_judge is not None) and self.confidence_threshold is None:
            raise ValueError("confidence_threshold is REQUIRED when 'judge' or 'multi_judge' is present")

        # escalate_to is REQUIRED when on_timeout is escalate and MUST NOT appear otherwise.
        if self.on_timeout == TimeoutAction.ESCALATE:
            if not self.escalate_to:
                raise ValueError("'escalate_to' is REQUIRED when on_timeout is 'escalate'")
        else:
            if self.escalate_to is not None:
                raise ValueError("'escalate_to' MUST NOT appear unless on_timeout is 'escalate'")

        return self


class Policies(AQEFBaseModel):
    validator_composition: str = Field("AND", pattern=r"^(AND|OR|hard-veto)$")
    weight: Optional[JSONNumber] = Field(None, gt=0)


class Contract(AQEFBaseModel):
    # Derived only; authored Contracts cannot supply this runtime provenance.
    _clause_weights: dict = PrivateAttr(default_factory=dict)
    name: Optional[str] = None
    constraints: List[Constraint] = Field(default_factory=list)
    expectations: List[Expectation] = Field(default_factory=list)
    policies: Optional[Policies] = None
    extends: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract(self) -> "Contract":
        # Appendix B §B.2:
        # Cross-field rule: at least one of constraints or expectations MUST be non-empty (or extends)
        if not self.constraints and not self.expectations and not self.extends:
            raise ValueError("A Contract MUST contain at least one Constraint or Expectation (or extend reusable contracts)")

        # Appendix B §B.3 Clause identity:
        # A clause id MUST be unique within the Contract that declares it.
        seen_ids = set()
        for c in self.constraints:
            if c.id:
                if c.id in seen_ids:
                    raise ValueError(f"Duplicate clause id '{c.id}' within Contract")
                seen_ids.add(c.id)
        for e in self.expectations:
            if e.id:
                if e.id in seen_ids:
                    raise ValueError(f"Duplicate clause id '{e.id}' within Contract")
                seen_ids.add(e.id)

        return self
