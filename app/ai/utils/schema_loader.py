import json
from pathlib import Path
from typing import Dict, Any


def load_schemas(schema_dir: str = "schemas") -> Dict[str, Any]:
    """
    Load all JSON schema files from the given directory into a dictionary.
    Keys will be the filename (without extension), values the parsed schema dict.

    Example:
        schemas/
            WineRackLayerTemplate.json
            OtherModel.json
        =>
        {
            "WineRackLayerTemplate": {...},
            "OtherModel": {...}
        }
    """
    schema_library: Dict[str, Any] = {}

    schema_path = Path(schema_dir)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema directory not found: {schema_dir}")

    for file in schema_path.glob("*.json"):
        with open(file, "r", encoding="utf-8") as f:
            schema = json.load(f)
            schema_name = file.stem
            schema_library[schema_name] = schema

    return schema_library
