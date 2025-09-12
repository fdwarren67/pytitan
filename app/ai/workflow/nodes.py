from typing import Dict, Any
from ..tools import InferSchemaTool, ValidateObjectTool, HydrateObjectTool
from .state import State


def infer_schema(state: State) -> Dict[str, Any]:
    """Infer schema from user input or return existing schema if available."""
    if state.schema_name and state.schema_def:
        return {
            "schema_name": state.schema_name,
            "schema_def": state.schema_def,
            "data": state.data or {},
        }
    output = InferSchemaTool.invoke(
        {"user_input": state.user_input, "schema_library": state.schema_library}
    )
    from .state import resolve_schema_name

    schema_name, schema_def = resolve_schema_name(
        output.get("schema"), state.schema_library or {}
    )
    # Preserve existing object data when inferring new schema
    existing_data = state.data or {}
    new_data = output.get("data", {})
    merged_data = {**existing_data, **new_data}
    return {
        "schema_name": schema_name,
        "schema_def": schema_def,
        "data": merged_data,
    }


def hydrate_object(state: State) -> Dict[str, Any]:
    """Hydrate object with data from user input."""
    hyd = HydrateObjectTool.invoke(
        {
            "user_input": state.user_input or "",
            "schema_def": state.schema_def or {},
            "schema_name": state.schema_name,
            "existing_object": state.data or {},
        }
    )
    # Always preserve existing data, only add new data from hydration
    new_data = hyd.get("data") or {}
    merged = {**(state.data or {}), **new_data}

    # Field validation is handled in the hydrate_object tool

    return {"data": merged}


def validate_object(state: State) -> Dict[str, Any]:
    """Validate object against schema."""
    if not state.schema_name or not state.schema_def:
        return {
            "validation_result": {
                "valid": False,
                "missing": [{"field": "schema_name", "message": "Schema is required"}],
            }
        }
    output = ValidateObjectTool.invoke(
        {
            "schema_name": state.schema_name,
            "schema_def": state.schema_def,
            "data": state.data or {},
        }
    )
    return {
        "validation_result": output,
        "data": state.data or {},  # Preserve the data from the state
    }
