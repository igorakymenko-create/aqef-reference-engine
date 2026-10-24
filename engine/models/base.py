"""Base model with strict validation settings for AQEF.

References:
- Appendix A, introduction ("A conformant implementation MUST accept configurations expressible within this specification")
- Review D-2 ("A configuration key the engine does not recognize should be rejected, naming the key, rather than dropped.")
"""

from pydantic import BaseModel, ConfigDict


class AQEFBaseModel(BaseModel):
    # Reject unknown keys across all configuration models rather than silently dropping them
    model_config = ConfigDict(extra="forbid")
