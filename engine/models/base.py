"""Base model with strict validation settings for AQEF.

References:
- Appendix A, introduction ("A conformant implementation MUST accept configurations expressible within this specification")
- Review D-2 ("A configuration key the engine does not recognize should be rejected, naming the key, rather than dropped.")
"""

from typing import Annotated, ClassVar, get_args, get_origin
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


JSONNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
JSONInteger = Annotated[int, Field(strict=True)]


class AQEFBaseModel(BaseModel):
    # Reject unknown keys across all configuration models rather than silently dropping them
    model_config = ConfigDict(extra="forbid")


class ConfigurationModel(AQEFBaseModel):
    """A/B: optional means omittable, not nullable; free JSON values are untouched."""
    nullable_fields: ClassVar[frozenset[str]] = frozenset()
    legacy_null_defaults: ClassVar[bool] = True

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = super().__get_pydantic_json_schema__(core_schema, handler)
        for name, field in schema.get("properties", {}).items():
            if name in cls.nullable_fields:
                continue
            if field.get("default", "absent") is None:
                field.pop("default")
            if "anyOf" in field:
                choices = [choice for choice in field["anyOf"] if choice.get("type") != "null"]
                if len(choices) == 1:
                    field.pop("anyOf")
                    field.update(choices[0])
                else:
                    field["anyOf"] = choices
        return schema

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if isinstance(value, dict):
            invalid = [name for name in cls.model_fields
                       if name in value and value[name] is None and name not in cls.nullable_fields]
            if invalid:
                raise ValueError("Explicit null is not allowed for field(s): " + ", ".join(invalid))
        return value

    @model_serializer(mode="wrap")
    def serialize_configuration(self, handler, info):
        data = handler(self)
        if info.mode == "json" and not (info.context or {}).get("include_absent"):
            return {key: value for key, value in data.items()
                    if value is not None or key in self.nullable_fields}
        return data


def normalize_legacy_configuration(annotation, value):
    """Remove legacy absent-field nulls only at schema-defined configuration positions."""
    if isinstance(annotation, type) and issubclass(annotation, ConfigurationModel) and isinstance(value, dict):
        fields = annotation.model_fields
        return {key: normalize_legacy_configuration(fields[key].annotation, child) if key in fields else child
                for key, child in value.items()
                if child is not None or key in annotation.nullable_fields or key not in fields or not annotation.legacy_null_defaults}
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is list and isinstance(value, list):
        return [normalize_legacy_configuration(args[0], child) for child in value]
    if origin is dict and isinstance(value, dict):
        return {key: normalize_legacy_configuration(args[1], child) for key, child in value.items()}
    for option in args if origin is not None else ():
        if isinstance(option, type) and issubclass(option, ConfigurationModel) and isinstance(value, dict):
            return normalize_legacy_configuration(option, value)
        if get_origin(option) in (list, dict):
            return normalize_legacy_configuration(option, value)
    return value
