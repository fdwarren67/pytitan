# FilterStuff.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union
import json

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Operator(str, Enum):
    EQ = "EQ"
    NE = "NE"
    LK = "LK"
    SW = "SW"
    EW = "EW"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NIN = "NIN"


class LogicalOperator(str, Enum):
    AND = "And"
    OR = "Or"


# ---------------------------------------------------------------------------
# Core filter models
# ---------------------------------------------------------------------------

@dataclass
class FilterExpression:
    """
    Basic component of a filter: a property (column), an operator, and a value.
    """
    property_name: str
    operator: Operator = Operator.EQ
    value: Any = ""

    # camelCase JSON helpers
    def to_dict(self) -> Dict[str, Any]:
        return {
            "propertyName": self.property_name,
            "operator": self.operator.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilterExpression":
        return cls(
            property_name=data["propertyName"],
            operator=Operator(data.get("operator", Operator.EQ.value)),
            value=data.get("value", ""),
        )


@dataclass
class FilterCollection:
    """
    Ragged hierarchy of FilterExpressions for complex comparisons.
    """
    logical_operator: LogicalOperator = LogicalOperator.AND
    collections: List["FilterCollection"] = field(default_factory=list)
    expressions: List["FilterExpression"] = field(default_factory=list)

    # camelCase JSON helpers
    def to_dict(self) -> Dict[str, Any]:
        return {
            "logicalOperator": self.logical_operator.value,
            "collections": [c.to_dict() for c in self.collections],
            "expressions": [e.to_dict() for e in self.expressions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilterCollection":
        return cls(
            logical_operator=LogicalOperator(data.get("logicalOperator", LogicalOperator.AND.value)),
            collections=[cls.from_dict(c) for c in data.get("collections", [])],
            expressions=[FilterExpression.from_dict(e) for e in data.get("expressions", [])],
        )


# ---------------------------------------------------------------------------
# JSON Schemas (optional validation if jsonschema is installed)
# ---------------------------------------------------------------------------

FILTER_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/filter.schema.json",
    "title": "Filter Collection",
    "$defs": {
        "FilterExpression": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "propertyName": {"type": "string", "minLength": 1},
                "operator": {
                    "type": "string",
                    "enum": ["EQ","NE","LK","SW","EW","GT","GTE","LT","LTE","IN","NIN"],
                },
                "value": {},
            },
            "required": ["propertyName", "value"],
            "allOf": [
                # For IN/NIN, value must be an array
                {
                    "if": {"properties": {"operator": {"enum": ["IN","NIN"]}}},
                    "then": {"properties": {"value": {"type": "array"}}},
                },
                # Otherwise, allow string or array of strings
                {
                    "properties": {
                        "value": {
                            "oneOf": [
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "string"},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"}
                            ]
                        }
                    }
                },
            ],
        },
        "FilterCollection": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "logicalOperator": {"type": "string", "enum": ["And","Or"]},
                "collections": {"type": "array", "items": {"$ref": "#/$defs/FilterCollection"}},
                "expressions": {"type": "array", "items": {"$ref": "#/$defs/FilterExpression"}},
            },
        },
    },
    "type": "object",
    "$ref": "#/$defs/FilterCollection",
}

def _validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """
    Validate with jsonschema if available; otherwise no-op.
    """
    try:
        import jsonschema
    except Exception:
        return
    jsonschema.validate(instance=instance, schema=schema)


def parse_filter_collection_json(
    payload: Union[str, Dict[str, Any]],
    *,
    validate: bool = True,
) -> FilterCollection:
    """
    Accept a JSON string or dict and return a FilterCollection.
    """
    data = json.loads(payload) if isinstance(payload, str) else payload
    if validate:
        _validate(data, FILTER_SCHEMA)
    return FilterCollection.from_dict(data)


# ---------------------------------------------------------------------------
# Search model with camelCase interop (includes entityName)
# ---------------------------------------------------------------------------

SEARCH_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/search.schema.json",
    "title": "Filter SearchModel",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entityName": {"type": "string", "minLength": 1},
        "columns": {"type": "array", "items": {"type": "string"}},
        "filter": {"$ref": "filter.schema.json#/$defs/FilterCollection"},
        "sort": {"type": "array", "items": {"type": "string"}},
        "pageSize": {"type": "integer", "minimum": 0},
        "pageIndex": {"type": "integer", "minimum": 0},
    },
    "required": ["entityName", "filter"],
}

@dataclass
class SearchModel:
    """
    Python-idiomatic model (snake_case) with camelCase JSON interop.
    """
    entity_name: str = ""
    columns: List[str] = field(default_factory=list)
    filter: FilterCollection = field(default_factory=FilterCollection)
    sort: List[str] = field(default_factory=list)
    page_size: int = 0
    page_index: int = 0

    # camelCase JSON helpers
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entityName": self.entity_name,
            "columns": list(self.columns),
            "filter": self.filter.to_dict(),
            "sort": list(self.sort),
            "pageSize": self.page_size,
            "pageIndex": self.page_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchModel":
        return cls(
            entity_name=str(data.get("entityName", "")),
            columns=list(data.get("columns", [])),
            filter=FilterCollection.from_dict(data.get("filter", {})),
            sort=list(data.get("sort", [])),
            page_size=int(data.get("pageSize", 0) or 0),
            page_index=int(data.get("pageIndex", 0) or 0),
        )


def _validate_search(instance: Dict[str, Any]) -> None:
    """
    Validate SearchModel JSON if jsonschema is available; otherwise no-op.
    Resolves the nested FilterCollection schema using an in-memory resolver.
    """
    try:
        import jsonschema
        from jsonschema import RefResolver
    except Exception:
        return

    # Use the filter schema as the base for resolver; it contains $defs we need.
    resolver = RefResolver.from_schema(FILTER_SCHEMA)
    jsonschema.validate(instance=instance, schema=SEARCH_SCHEMA, resolver=resolver)


def parse_search_model_json(
    payload: Union[str, Dict[str, Any]],
    *,
    validate: bool = True,
) -> SearchModel:
    """
    Accept camelCase JSON for SearchModel, return a SearchModel instance.
    Also validates the nested FilterCollection when validation is enabled.
    """
    data = json.loads(payload) if isinstance(payload, str) else payload
    if validate:
        _validate_search(data)
        _validate(data.get("filter", {}), FILTER_SCHEMA)
    return SearchModel.from_dict(data)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "Operator",
    "LogicalOperator",
    "FilterExpression",
    "FilterCollection",
    "FILTER_SCHEMA",
    "parse_filter_collection_json",
    "SearchModel",
    "SEARCH_SCHEMA",
    "parse_search_model_json",
]
