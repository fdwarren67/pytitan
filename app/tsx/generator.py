import re, datetime as dt
from typing import Any, List
from decimal import Decimal

_camel_word_re = re.compile(r'[^0-9A-Za-z]+')

def _to_camel(name: str) -> str:
    cleaned = _camel_word_re.sub(' ', str(name)).strip()
    if not cleaned:
        return str(name)
    parts = cleaned.split()
    head = parts[0].lower()
    tail = [p[:1].upper() + p[1:].lower() for p in parts[1:]]
    return head + ''.join(tail)

def _as_name(col: Any) -> str:
    if isinstance(col, dict):
        return str(col.get("name") or col.get("label") or col.get("column") or "")
    return str(col)

def _to_pascal(s: str) -> str:
    cleaned = _camel_word_re.sub(' ', s).strip()
    if not cleaned:
        return "Result"
    return ''.join(p[:1].upper() + p[1:].lower() for p in cleaned.split())

def _infer_ts_scalar_type(v: Any) -> str:
    # Map Python runtime values to TS primitives.
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float, Decimal)):
        return "number"
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        # JSON encodes these as strings; using string in TS keeps things simple.
        return "string"
    if isinstance(v, (list, tuple)):
        return "unknown[]"
    if isinstance(v, dict):
        return "Record<string, unknown>"
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "string"
    if isinstance(v, str):
        return "string"
    return "unknown"

def _infer_ts_type_for_column(samples: List[Any]) -> str:
    # Collect observed types across sample values.
    kinds = { _infer_ts_scalar_type(v) for v in samples }
    # Separate nulls from non-nulls
    non_null = kinds - {"null"}
    has_null = "null" in kinds

    # If heterogeneous non-null types, fall back to 'unknown' (plus null if present).
    if len(non_null) == 0:
        base = "unknown"
    elif len(non_null) == 1:
        base = next(iter(non_null))
    else:
        base = "unknown"

    return f"{base} | null" if has_null else base