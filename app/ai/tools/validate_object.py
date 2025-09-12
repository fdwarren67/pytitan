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


def validate_with_clarification(model_cls, schema: dict, data: dict) -> dict:
    try:
        obj = model_cls(**(data or {}))
        # ⬇️ drop nulls so optional fields don’t appear as null
        cleaned = obj.model_dump(exclude_none=True)

        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(cleaned), key=lambda e: e.path)
        if errors:
            e = errors[0]  # return one missing field at a time
            # pull a field name if it’s a required-missing error; else use path
            msg = e.message
            field = (
                "'{}'".format(msg.split("'")[1])
                if "is a required property" in msg
                else ".".join(map(str, e.path)) or "?"
            )
            return {
                "valid": False,
                "missing": [{"field": field.strip("'"), "message": msg}],
            }

        return {"valid": True, "object": cleaned}

    except ValidationError as pe:
        e0 = (pe.errors() or [{}])[0]
        return {
            "valid": False,
            "missing": [
                {
                    "field": ".".join(map(str, e0.get("loc", []))) or "?",
                    "message": e0.get("msg", "invalid value"),
                }
            ],
        }


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
