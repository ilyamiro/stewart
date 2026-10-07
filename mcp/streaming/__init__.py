"""Streaming package for searching, resolving, and opening movies and TV series
using top sites and player aggregators from FMHY (freemediaheckyeah).
"""

from .providers import STREAMING_PROVIDERS, Provider
from .service import StreamingService

__all__ = ["STREAMING_PROVIDERS", "Provider", "StreamingService"]
