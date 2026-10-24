"""Dataset models and schemas.

References:
- Volume IV — Dataset Engine (§Static, §Versioning)
- Appendix A §A.8
- Appendix B §B.2, §B.3
- Implementer's Brief §3 (Scope: Static datasets only)
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class DatasetSource(str, Enum):
    STATIC = "static"
    SYNTHETIC = "synthetic"
    GENERATED = "generated"
    PRODUCTION_REPLAY = "production_replay"


class Row(BaseModel):
    id: str = Field(..., min_length=1)
    variables: Dict[str, Any] = Field(default_factory=dict)


class Dataset(BaseModel):
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    source: DatasetSource
    rows: Optional[List[Row]] = None
    base_dataset: Optional[str] = None

    @model_validator(mode="after")
    def validate_dataset(self) -> "Dataset":
        # BRIEF.md §3 Scope:
        # Not in scope: Dataset sources other than Static; reject a configuration that needs it.
        if self.source != DatasetSource.STATIC:
            raise ValueError(f"Dataset source '{self.source.value}' is not supported; only 'static' is in scope")

        # Appendix B §B.2 Dataset:
        # When source is static: rows REQUIRED.
        if self.rows is None:
            raise ValueError("When dataset source is 'static', 'rows' is REQUIRED")

        # Row IDs must be unique within dataset
        seen_row_ids = set()
        for r in self.rows:
            if r.id in seen_row_ids:
                raise ValueError(f"Duplicate row id '{r.id}' in Dataset '{self.name}@{self.version}'")
            seen_row_ids.add(r.id)

        return self
