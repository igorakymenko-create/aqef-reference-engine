"""The AQEF reference REST API client."""

from ._operations import Operations
from ._transport import APIError, TransportError


class Client(Operations):
    """An authenticated, synchronous AQEF REST client."""


__all__ = ["APIError", "Client", "TransportError"]
__version__ = "0.1.0"
