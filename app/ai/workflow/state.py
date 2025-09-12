from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel


class State(BaseModel):
    user_input: Optional[str] = None
    schema_name: Optional[str] = None
    schema_def: Optional[Dict[str, Any]] = None  # Renamed to avoid shadowing
    schema_library: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None


def resolve_schema_name(
    schema_name: Optional[str], schema_library: dict
) -> Tuple[Optional[str], Optional[dict]]:
    """Resolve schema name with fuzzy matching."""
    if not schema_name:
        return None, None
    if schema_name in schema_library:
        return schema_name, schema_library[schema_name]
    for key in schema_library:
        if key.lower() == schema_name.lower():
            return key, schema_library[key]
    norm = schema_name.replace("_", "").replace("-", "").lower()
    for key in schema_library:
        if key.replace("_", "").replace("-", "").lower() == norm:
            return key, schema_library[key]
    return None, None
