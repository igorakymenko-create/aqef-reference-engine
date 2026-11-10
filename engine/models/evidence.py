"""Stored Conversation form shared by execution and A.4 FixedEvidence."""
from pydantic import Field, StrictStr, model_validator

from engine.models.base import AQEFBaseModel


class Turn(AQEFBaseModel):
    prompt: StrictStr
    response: StrictStr | None = Field(default=None, exclude_if=lambda value: value is None)
    tool_calls: list[dict] | None = Field(default=None, min_length=1, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def one_output(self):
        if (self.response is None) == (self.tool_calls is None):
            raise ValueError("A turn requires either response or tool_calls")
        return self


class Conversation(AQEFBaseModel):
    turns: list[Turn] = Field(min_length=1)
