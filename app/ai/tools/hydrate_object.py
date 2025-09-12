# titan/ai/hydrate_object.py
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser


# ---- helpers -----------------------------------------------------------------
def _build_field_catalog(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    props = (schema or {}).get("properties", {}) or {}
    required = set((schema or {}).get("required", []) or [])
    out: List[Dict[str, Any]] = []
    for name, spec in props.items():
        spec = spec or {}
        item = {
            "name": name,
            "type": spec.get("type"),
            "required": name in required,
            "description": spec.get("description") or "",
        }
        if isinstance(spec.get("enum"), list):
            item["enum"] = spec["enum"]
        out.append(item)
    return out


def _build_conditional_rules(schema: Dict[str, Any]) -> str:
    """Extract conditional schema rules (if/then/else) for the AI to understand."""
    rules = []

    # Check for allOf with conditional rules
    all_of = schema.get("allOf", [])
    for rule in all_of:
        if "if" in rule and "then" in rule:
            if_condition = rule["if"]
            then_condition = rule["then"]

            # Extract the condition
            if "properties" in if_condition:
                for field, field_spec in if_condition["properties"].items():
                    if "enum" in field_spec:
                        enum_values = field_spec["enum"]
                        if (
                            "required" in if_condition
                            and field in if_condition["required"]
                        ):
                            # Extract required fields from then condition
                            then_required = then_condition.get("required", [])
                            if then_required:
                                rules.append(
                                    f"When {field} is {enum_values}, then {', '.join(then_required)} is required"
                                )

    return "\n".join(rules) if rules else ""


# ---- prompt ------------------------------------------------------------------
_prompt = ChatPromptTemplate.from_template(
    """
    You are a structured data extractor.
    Hydrate an object that matches the provided JSON Schema fields using ONLY facts from the user's request.
    {existing_object_context}

    --- Schema Name ---
    {schema_name}

    --- Field Catalog (name, type, required, description, enum) ---
    {field_catalog}

    --- Conditional Rules ---
    {conditional_rules}

    --- User Request ---
    {user_input}

    CRITICAL: Use ONLY the exact field names from the Field Catalog above.
    
    Rules:
    - Output valid JSON with exactly one top-level key: "data".
    - "data" must contain only fields explicitly present in the user request.
    - Use EXACT field names from the Field Catalog. Do NOT create new field names.
    - Do NOT guess, infer hidden defaults, or convert units.
    - Preserve literal strings; parse numbers and booleans when unambiguous.
    - Omit any field that is not clearly provided by the user.
    - Pay attention to conditional rules above - they specify which fields are required based on other field values.
    - If nothing is extractable, return: {{ "data": {{}} }}

    Examples:
    Example A (WineRackLayerTemplate with spacing)
    {{ "data": {{ "alignment": "left", "spacing": 660 }} }}

    Example B (WineRackLayerTemplate with count)
    {{ "data": {{ "alignment": "justify", "count": 6 }} }}

    Example C (nothing extractable)
    {{ "data": {{}} }}
    """
)

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
_parser = JsonOutputParser()
_chain = _prompt | _llm | _parser


# ---- tool function -----------------------------------------------------------
def hydrate_object(
    user_input: str,
    schema_def: Dict[str, Any],
    schema_name: Optional[str] = None,
    existing_object: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    field_catalog = _build_field_catalog(schema_def)
    conditional_rules = _build_conditional_rules(schema_def)

    # Build context for existing object
    existing_object_context = ""
    if existing_object:
        existing_object_context = f"""
    --- Existing Object Data ---
    {json.dumps(existing_object, ensure_ascii=False)}
    
    IMPORTANT: You already have an existing object with the above data. The user request may contain additional information to add to or update this existing object. 
    
    - Only extract NEW information from the user request that is not already in the existing object
    - Do NOT repeat or re-extract data that already exists in the existing object
    - The final result should be a combination of existing data + new data from the user request
    - If the user request contains no new extractable information, return an empty data object: {{ "data": {{}} }}
    """

    resp = _chain.invoke(
        {
            "schema_name": schema_name or schema_def.get("title") or "",
            "field_catalog": json.dumps(field_catalog, ensure_ascii=False),
            "conditional_rules": conditional_rules,
            "user_input": user_input,
            "existing_object_context": existing_object_context,
        }
    )

    if isinstance(resp, dict):
        result = resp
    elif hasattr(resp, "content"):
        result = json.loads(resp.content.strip())
    else:
        raise ValueError(f"Unexpected response type: {type(resp)}")

    # Guards
    data = result.get("data")
    if not isinstance(data, dict):
        data = {}

    # Validate field names against schema
    schema_properties = schema_def.get("properties", {})
    valid_field_names = set(schema_properties.keys())

    # Remove any fields that don't match the schema
    invalid_fields = []
    for field_name in list(data.keys()):
        if field_name not in valid_field_names:
            invalid_fields.append(field_name)
            del data[field_name]

    if invalid_fields:
        print(
            f"WARNING: Removed invalid field names: {invalid_fields}. Valid fields are: {list(valid_field_names)}"
        )

    return {"data": data}


# ---- Structured Tool ---------------------------------------------------------
class HydrateObjectInput(BaseModel):
    user_input: str = Field(..., description="Original natural-language user request.")
    schema_def: Dict[str, Any] = Field(
        ..., description="Full JSON Schema definition to target."
    )
    schema_name: Optional[str] = Field(
        None, description="Optional display name for the schema."
    )
    existing_object: Optional[Dict[str, Any]] = Field(
        None, description="Existing object data to build upon."
    )


HydrateObjectTool = StructuredTool.from_function(
    func=hydrate_object,
    name="HydrateObject",
    description="Hydrate a candidate object from user input using the provided JSON Schema definition.",
    args_schema=HydrateObjectInput,
)
