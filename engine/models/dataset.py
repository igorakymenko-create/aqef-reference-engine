"""Dataset models and schemas.

References:
- Volume IV — Dataset Engine (§Static, §Versioning)
- Appendix A §A.8
- Appendix B §B.2, §B.3
"""

from datetime import date, datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import Field, StrictBool, field_validator, model_validator
from engine.models.base import ConfigurationModel as AQEFBaseModel, JSONInteger
from engine.models.evidence import Conversation


class DatasetSource(str, Enum):
    STATIC = "static"
    SYNTHETIC = "synthetic"
    GENERATED = "generated"
    PRODUCTION_REPLAY = "production_replay"


class MechanismType(str, Enum):
    DATA_MUTATION = "data_mutation"
    FUZZING = "fuzzing"
    EDGE_CASES = "edge_cases"
    ADVERSARIAL = "adversarial"


class MechanismConfig(AQEFBaseModel):
    # Appendix A §A.8, Appendix B §B.2:
    # type | String | MUST | data_mutation, fuzzing, edge_cases, or adversarial.
    type: MechanismType = Field(...)
    transforms: Optional[List[Dict[str, Any]]] = None
    perturbations: Optional[List[Dict[str, Any]]] = None


class Row(AQEFBaseModel):
    id: str = Field(..., min_length=1)
    variables: Dict[str, Any]


class GeneratorConfig(AQEFBaseModel):
    model: str = Field(min_length=1)
    seed: JSONInteger | None = None
    instruction: str = Field(min_length=1)


class CaptureConfig(AQEFBaseModel):
    source: str = Field(min_length=1)
    date_range: tuple[date, date]
    sampling: str = Field(min_length=1)
    sample_size: JSONInteger = Field(gt=0)
    anonymization: StrictBool

    @field_validator("date_range", mode="before")
    @classmethod
    def date_only(cls, value):
        if not isinstance(value, (list, tuple)) or any(
            type(item) is not date and
            (not isinstance(item, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item))
            for item in value
        ):
            raise ValueError("capture.date_range must contain ISO calendar dates")
        return value

    @model_validator(mode="after")
    def ordered_range(self):
        if self.date_range[0] > self.date_range[1]:
            raise ValueError("capture.date_range must be ordered")
        return self


class DatasetDefinition(AQEFBaseModel):
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    source: DatasetSource = Field(...)
    rows: Optional[List[Row]] = None
    generator: GeneratorConfig | None = None
    capture: CaptureConfig | None = None
    base_dataset: Optional[str] = Field(None, pattern=r"^.+@.+$")
    mechanisms: Optional[List[MechanismConfig]] = None

    @model_validator(mode="after")
    def validate_dataset(self):
        if self.mechanisms:
            types = ", ".join(m.type.value for m in self.mechanisms)
            raise ValueError(f"mechanisms: dataset_mechanism capabilities are not offered ({types})")
        if self.source == DatasetSource.SYNTHETIC:
            raise ValueError("Dataset source 'synthetic' is reserved")
        for field, source in (("generator", DatasetSource.GENERATED),
                              ("capture", DatasetSource.PRODUCTION_REPLAY)):
            if (getattr(self, field) is not None) != (self.source == source):
                raise ValueError(f"'{field}' is required for source '{source.value}' and forbidden otherwise")
        if self.source == DatasetSource.STATIC and self.rows is None:
            raise ValueError("When dataset source is 'static', 'rows' is REQUIRED")

        # Row IDs must be unique within dataset
        seen_row_ids = set()
        for r in self.rows or []:
            if r.id in seen_row_ids:
                raise ValueError(f"Duplicate row id '{r.id}' in Dataset '{self.name}@{self.version}'")
            seen_row_ids.add(r.id)

        return self


class DatasetInput(DatasetDefinition):
    @model_validator(mode="after")
    def reject_supplied_rows(self):
        if self.source != DatasetSource.STATIC and self.rows is not None:
            raise ValueError("Non-static Dataset rows come only from generation or capture")
        return self


class Dataset(DatasetDefinition):
    generated_at: datetime | None = None
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def require_materialized_version(self):
        if self.rows is None:
            raise ValueError("Register non-static Dataset versions through the Dataset API")
        for field, source in (("generated_at", DatasetSource.GENERATED),
                              ("captured_at", DatasetSource.PRODUCTION_REPLAY)):
            if (getattr(self, field) is not None) != (self.source == source):
                raise ValueError(f"'{field}' must be recorded by the Dataset API for source '{source.value}'")
        if self.source == DatasetSource.PRODUCTION_REPLAY:
            for row in self.rows:
                if set(row.variables) != {"conversation"}:
                    raise ValueError("Production Replay Rows must contain a captured conversation")
                Conversation.model_validate(row.variables["conversation"])
        return self
