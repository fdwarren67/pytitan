from typing import Optional
from ..tools import ClarifyFieldTool
from .state import State


def handle_validation_errors(result: dict, schema_library: dict) -> Optional[State]:
    """Handle validation errors by preparing clarification data for API response."""
    validation = result.get("validation_result", {})
    if not validation or validation.get("valid"):
        return None

    missing = validation.get("missing", [])
    if not missing:
        return None

    field = missing[0]["field"]
    msg = missing[0]["message"]
    spec = (result.get("schema_def") or {}).get("properties", {}).get(field, {}) or {}
    expected_type = spec.get("type")
    enum_values = spec.get("enum")

    q = ClarifyFieldTool.invoke(
        {
            "field_name": field,
            "field_type": expected_type,
            "description": spec.get("description"),
            "allowed_values": enum_values,
        }
    )["question"]

    # Instead of prompting user directly, return None to indicate clarification is needed
    # The API will return the clarification question to the client
    return None
