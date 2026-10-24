"""Runtime C.7 Results and C.3 Admission inputs."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from engine.models.base import AQEFBaseModel


class Result(AQEFBaseModel):
    id: str
    execution: str
    clause: str
    oracle_type: Literal["validator", "judge", "human_reviewer"]
    oracle: str
    verdict: Literal["pass", "fail"] | None
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | Literal["not_applicable"]
    disposition: Literal["actionable", "inconclusive", "awaiting_review", "oracle_unavailable", "not_assessed"]
    supporting_evidence: dict
    recorded_at: datetime
    resolves: str | None = None
    assertions: StrictInt | None = Field(default=None, gt=1)

    @model_validator(mode="after")
    def consistency(self):
        from engine.validators import number
        if self.assertions is not None and self.oracle_type != "judge":
            raise ValueError("assertions applies only to Judge Results")
        if self.verdict is None:
            if self.disposition not in ("awaiting_review", "oracle_unavailable", "not_assessed") or self.confidence != "not_applicable":
                raise ValueError("No-verdict Result requires unavailable/pending disposition and inapplicable Confidence")
        else:
            if self.disposition not in ("actionable", "inconclusive"):
                raise ValueError("Verdict requires actionable or inconclusive disposition")
            if self.oracle_type == "validator":
                if self.confidence != "not_applicable" or self.disposition != "actionable":
                    raise ValueError("Validator verdict is actionable with inapplicable Confidence")
            elif self.oracle_type == "judge" and (not 0 <= number(self.confidence) <= 1):
                raise ValueError("Judge Confidence must be in [0,1]")
        return self


class AdmissionRequest(AQEFBaseModel):
    oracle: StrictStr = Field(min_length=1)
    reference_set: StrictStr = Field(pattern=r"^[^@\s]+@[^@\s]+$")
    items: StrictInt = Field(ge=1)
    verdict_distribution: dict[StrictStr, StrictInt]
    raw_agreement: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    measure: StrictStr = Field(min_length=1)
    chance_corrected_agreement: float | Literal["not_computed"] = Field(union_mode="left_to_right")
    threshold: float = Field(strict=True, allow_inf_nan=False)
    admitted: StrictBool
    labelled_by: list[StrictStr] = Field(min_length=1)
    arbitrations: list[StrictStr] | None = None

    @model_validator(mode="before")
    @classmethod
    def strict_chance(cls, value):
        from engine.validators import number
        if isinstance(value, dict) and value.get("chance_corrected_agreement") != "not_computed":
            number(value.get("chance_corrected_agreement"))
        return value

    @model_validator(mode="after")
    def consistency(self):
        if any(k not in ("pass", "fail") or v < 0 for k, v in self.verdict_distribution.items()):
            raise ValueError("verdict_distribution requires nonnegative pass/fail counts")
        if sum(self.verdict_distribution.values()) != self.items:
            raise ValueError("verdict_distribution must sum to items")
        expected = self.chance_corrected_agreement != "not_computed" and self.chance_corrected_agreement >= self.threshold
        if self.admitted != expected:
            raise ValueError("admitted must equal whether chance_corrected_agreement meets threshold")
        if any(not s.strip() for s in [self.oracle, self.measure, *self.labelled_by, *(self.arbitrations or [])]):
            raise ValueError("Admission identifiers cannot be blank")
        if "arbitrations" in self.model_fields_set and self.arbitrations is None:
            raise ValueError("arbitrations must be a list when supplied")
        return self
