# titan/ai/schema_validator.py
from typing import Dict, Any
from pydantic import BaseModel, Field, ValidationError, create_model
from langchain.tools import StructuredTool
from jsonschema import Draft7Validator


def build_model_from_schema(name: str, schema: Dict[str, Any]) -> type[BaseModel]:
    fields = {}
    props = schema.get("properties", {}) or {}
    required_set = set(schema.get("required", []) or [])

    for prop, spec in props.items():
        spec = spec or {}
        t = spec.get("type")
        py = str
        if t == "integer":
            py = int
        elif t == "number":
            py = float
        elif t == "boolean":
            py = bool
        # note: strings and enums stay as str; JSON Schema pass enforces enum values
        default = ... if prop in required_set else None
        fields[prop] = (py, Field(default, description=spec.get("description")))
    return create_model(name, **fields)  # type: ignore


def validate_with_clarification(model_cls, schema: dict, data: dict, schema_name: str = None) -> dict:
    """
    Validate data against JSON schema, properly handling conditional requirements.
    """
    cleaned = data or {}
    
    
    # Default validation for other schemas
    from jsonschema import Draft7Validator
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(cleaned))
    
    if errors:
        missing_fields = []
        schema_properties = schema.get("properties", {})
        
        for error in errors:
            # Extract field name from error message
            if "is a required property" in error.message:
                field_name = error.message.split("'")[1]
            else:
                field_name = ".".join(map(str, error.path)) if error.path else "unknown"
            
            field_spec = schema_properties.get(field_name, {})
            field_type = field_spec.get("type", "string")
            
            missing_fields.append({
                "field": field_name,
                "message": error.message,
                "field_type": field_type
            })
        
        return {
            "valid": False,
            "missing": missing_fields,
        }
    
    return {"valid": True, "object": cleaned}


class ValidatorInput(BaseModel):
    schema_name: str
    schema_def: Dict[str, Any]  # Renamed to avoid shadowing
    data: Dict[str, Any]


def _schema_validator_tool_fn(
    schema_name: str, schema_def: Dict[str, Any], data: Dict[str, Any]
) -> Dict[str, Any]:
    model_cls = build_model_from_schema(schema_name, schema_def)
    return validate_with_clarification(model_cls, schema_def, data)


ValidateObjectTool = StructuredTool.from_function(
    func=_schema_validator_tool_fn,
    name="ValidateObject",
    description="Validate JSON against a schema (including if/then/else) and return either a valid object or missing fields.",
    args_schema=ValidatorInput,
)
