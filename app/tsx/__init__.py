"""
TypeScript generation module for the Pytitan data service.

This module provides TypeScript class generation from query results.
"""

from .generator import (
    _to_camel,
    _as_name,
    _to_pascal,
    _infer_ts_type_for_column,
)

__all__ = [
    "_to_camel",
    "_as_name",
    "_to_pascal",
    "_infer_ts_type_for_column",
]
