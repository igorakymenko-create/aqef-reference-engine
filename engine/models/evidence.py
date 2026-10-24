"""Stored Conversation form shared by execution and A.4 FixedEvidence."""
from pydantic import Field, StrictStr

from engine.models.base import AQEFBaseModel


class Turn(AQEFBaseModel):
    prompt: StrictStr
    response: StrictStr


class Conversation(AQEFBaseModel):
    turns: list[Turn] = Field(min_length=1)
