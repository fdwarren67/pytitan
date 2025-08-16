from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple, Union, Iterable, Optional
import re

from .myfilter import (
    FilterCollection,
    FilterExpression,
    Operator,
    LogicalOperator,
    SearchModel,
)

_UNQUOTED_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

def _quote_identifier(name: str, *, quote_identifiers: bool) -> str:
    """
    Quote an identifier if needed. Doubles internal quotes.
    """
    if not quote_identifiers and _UNQUOTED_IDENT_RE.match(name):
        return name
    return f"\"{name.replace('\"', '\"\"')}\""

def _quote_dotted_identifier(name: str, *, quote_identifiers: bool) -> str:
    """
    Quote a possibly dotted identifier (e.g., db.schema.table).
    """
    parts = [p.strip() for p in name.split(".")]
    return ".".join(_quote_identifier(p, quote_identifiers=quote_identifiers) for p in parts)

def _escape_like(value: str) -> str:
    """
    Escape \, %, _ in LIKE patterns. We'll use ESCAPE '\\' in SQL.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("%", "\\%").replace("_", "\\_")
    return value

class _ParamSink:
    """
    Collects params and returns the correct placeholder per paramstyle.
      - 'qmark'    -> ?, params is a list
      - 'pyformat' -> %(p1)s, params is a dict
    """
    def __init__(self, paramstyle: str = "qmark", *, prefix: str = "p", start_index: int = 1):
        if paramstyle not in {"qmark", "pyformat"}:
            raise ValueError("paramstyle must be 'qmark' or 'pyformat'")
        self.paramstyle = paramstyle
        self.prefix = prefix
        self.next_idx = start_index
        self.params_list: List[Any] = []
        self.params_dict: Dict[str, Any] = {}

    def add(self, value: Any) -> str:
        if self.paramstyle == "qmark":
            self.params_list.append(value)
            return "?"
        else:
            name = f"{self.prefix}{self.next_idx}"
            self.next_idx += 1
            self.params_dict[name] = value
            return f"%({name})s"

    def bundle(self) -> Union[List[Any], Dict[str, Any]]:
        return self.params_list if self.paramstyle == "qmark" else self.params_dict

def _format_like_pattern(val: str, op: Operator) -> str:
    lit = _escape_like(str(val))
    if op.value == "LK":
        return f"%{lit}%"
    if op.value == "SW":
        return f"{lit}%"
    if op.value == "EW":
        return f"%{lit}"
    raise AssertionError("LIKE pattern requested for non-like operator")

def _normalize_in_values(raw: Union[str, Sequence[Any]]) -> List[Any]:
    """
    Accepts either a comma-delimited string or a sequence; returns a list of strings.
    """
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip() != ""]
    else:
        items = list(raw)
    return [str(x) for x in items]

def _build_expr_sql(
    e: FilterExpression,
    sink: _ParamSink,
    *,
    use_ilike: bool,
    quote_identifiers: bool,
) -> str:
    col = _quote_identifier(e.property_name, quote_identifiers=quote_identifiers)
    op  = e.operator

    # LIKE / ILIKE family
    if op in (Operator.LK, Operator.SW, Operator.EW):
        patt = _format_like_pattern(e.value, op)
        ph = sink.add(patt)
        like_kw = "ILIKE" if use_ilike else "LIKE"
        return f"{col} {like_kw} {ph} ESCAPE '\\'"

    # IN / NOT IN
    if op in (Operator.IN, Operator.NIN):
        vals = _normalize_in_values(e.value)
        if not vals:
            # IN () is always false; NOT IN () is always true
            return "1=0" if op == Operator.IN else "1=1"
        phs = ", ".join(sink.add(str(v)) for v in vals)
        neg = "NOT " if op == Operator.NIN else ""
        return f"{col} {neg}IN ({phs})"

    # Scalar compares
    rhs = sink.add(str(e.value))
    if op == Operator.EQ:  return f"{col} = {rhs}"
    if op == Operator.NE:  return f"{col} <> {rhs}"
    if op == Operator.GT:  return f"{col} > {rhs}"
    if op == Operator.GTE: return f"{col} >= {rhs}"
    if op == Operator.LT:  return f"{col} < {rhs}"
    if op == Operator.LTE: return f"{col} <= {rhs}"

    raise ValueError(f"Unsupported operator: {op}")

def _combine(parts: List[str], logical: LogicalOperator) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return f"({parts[0]})"
    joiner = " AND " if logical == LogicalOperator.AND else " OR "
    return "(" + joiner.join(parts) + ")"

def build_where_clause_and_params(
    root: FilterCollection,
    *,
    paramstyle: str = "qmark",        # 'qmark' -> ?,  'pyformat' -> %(p1)s
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    default_when_empty: str = "1=1",
    include_where_keyword: bool = True,
    param_name_prefix: str = "p",
    param_start_index: int = 1,
) -> Tuple[str, Union[List[Any], Dict[str, Any]]]:
    """
    Returns (where_sql, params). If `include_where_keyword` is True,
    where_sql will be 'WHERE ...'; otherwise it's just the predicate text.
    """
    sink = _ParamSink(paramstyle, prefix=param_name_prefix, start_index=param_start_index)

    def walk(node: FilterCollection) -> str:
        parts: List[str] = []
        for e in node.expressions:
            parts.append(_build_expr_sql(e, sink, use_ilike=use_ilike, quote_identifiers=quote_identifiers))
        for c in node.collections:
            child = walk(c)
            if child:
                parts.append(child)
        return _combine(parts, node.logical_operator)

    body = walk(root).strip()
    if not body:
        body = default_when_empty
    else:
        # drop outer parens for prettiness
        if body.startswith("(") and body.endswith(")"):
            body = body[1:-1]

    where_sql = f"WHERE {body}" if include_where_keyword else body
    return where_sql, sink.bundle()

# -----------------------------------------------------------------------------
# SELECT builder
# -----------------------------------------------------------------------------
def _normalize_columns(columns: Iterable[str], *, quote_identifiers: bool) -> str:
    """
    Turn a list of column names/expressions into a SELECT list.
    - If empty -> '*'
    - '*' is passed through as-is.
    - Dotted identifiers are quoted segment-by-segment when quoting enabled.
    - If a column looks like an expression (contains space or '(' or ')'),
      it is passed through (trusted input).
    """
    cols = list(columns or [])
    if not cols:
        return "*"

    out: List[str] = []
    for c in cols:
        s = c.strip()
        if s == "*":
            out.append("*")
        elif any(tok in s for tok in (" ", "(", ")")):
            out.append(s)  # treat as expression
        elif "." in s:
            out.append(_quote_dotted_identifier(s, quote_identifiers=quote_identifiers))
        else:
            out.append(_quote_identifier(s, quote_identifiers=quote_identifiers))
    return ", ".join(out)

def _parse_sort_item(item: str) -> Tuple[str, str]:
    """
    Accepts:
      - '-age'            -> ('age','DESC')
      - 'age'             -> ('age','ASC')
      - 'age DESC'        -> ('age','DESC')
      - 'age:desc'        -> ('age','DESC')
    """
    s = item.strip()
    if not s:
        return ("", "ASC")

    if s.startswith("-"):
        return (s[1:].strip(), "DESC")

    if ":" in s and s.count(":") == 1:
        col, dir_ = s.split(":")
        d = dir_.strip().upper()
        return (col.strip(), "DESC" if d in ("DESC", "D") else "ASC")

    parts = s.split()
    if len(parts) == 2 and parts[1].upper() in ("ASC", "DESC"):
        return (parts[0].strip(), parts[1].upper())

    return (s, "ASC")

def _build_order_by(sort_list: Iterable[str], *, quote_identifiers: bool) -> str:
    pairs = [p for p in (_parse_sort_item(x) for x in (sort_list or [])) if p[0]]
    if not pairs:
        return ""
    rendered: List[str] = []
    for col, direction in pairs:
        if "." in col:
            ident = _quote_dotted_identifier(col, quote_identifiers=quote_identifiers)
        elif any(tok in col for tok in (" ", "(", ")")):
            ident = col  # expression
        else:
            ident = _quote_identifier(col, quote_identifiers=quote_identifiers)
        rendered.append(f"{ident} {direction}")
    return "ORDER BY " + ", ".join(rendered)

@dataclass
class SelectBuildResult:
    sql: str
    params: Union[List[Any], Dict[str, Any]]
    count_sql: Optional[str] = None
    count_params: Optional[Union[List[Any], Dict[str, Any]]] = None

def build_select_from_search(
    sm: SearchModel,
    *,
    paramstyle: str = "qmark",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
    include_count: bool = False,
) -> SelectBuildResult:
    """
    Build a complete SELECT (Snowflake-friendly) from SearchModel.
    - SELECT list from sm.columns (expressions passed through)
    - FROM from sm.entity_name (supports db.schema.table)
    - WHERE from sm.filter (parametrized)
    - ORDER BY from sm.sort (supports '-col', 'col DESC', 'col:desc')
    - LIMIT/OFFSET from sm.page_size / sm.page_index
    """
    if not sm.entity_name:
        raise ValueError("SearchModel.entity_name is required")

    select_list = _normalize_columns(sm.columns, quote_identifiers=quote_identifiers)
    distinct_kw = "DISTINCT " if distinct else ""
    from_name = _quote_dotted_identifier(sm.entity_name, quote_identifiers=quote_identifiers)

    # WHERE (skip adding WHERE if filter is empty)
    where_body, params = build_where_clause_and_params(
        sm.filter,
        paramstyle=paramstyle,
        use_ilike=use_ilike,
        quote_identifiers=quote_identifiers,
        include_where_keyword=False,
        default_when_empty="",  # IMPORTANT: don't emit WHERE 1=1 in SELECT
    )
    where_clause = f"WHERE {where_body}" if where_body.strip() else ""

    order_clause = _build_order_by(sm.sort, quote_identifiers=quote_identifiers)

    # Paging
    limit_clause = ""
    if sm.page_size and sm.page_size > 0:
        limit_clause = f"LIMIT {int(sm.page_size)}"
        if sm.page_index and sm.page_index > 0:
            offset = int(sm.page_index) * int(sm.page_size)
            limit_clause += f" OFFSET {offset}"

    sql = f"SELECT {distinct_kw}{select_list} FROM {from_name}"
    if where_clause:
        sql += f" {where_clause}"
    if order_clause:
        sql += f" {order_clause}"
    if limit_clause:
        sql += f" {limit_clause}"

    # Optional COUNT(*) mirror
    count_sql = None
    count_params = None
    if include_count:
        where_only, count_params = build_where_clause_and_params(
            sm.filter,
            paramstyle=paramstyle,
            use_ilike=use_ilike,
            quote_identifiers=quote_identifiers,
            include_where_keyword=False,
            default_when_empty="",  # mirror behavior
        )
        if where_only.strip():
            count_sql = f"SELECT COUNT(*) FROM {from_name} WHERE {where_only}"
        else:
            count_sql = f"SELECT COUNT(*) FROM {from_name}"

    return SelectBuildResult(sql=sql, params=params, count_sql=count_sql, count_params=count_params)

# -----------------------------------------------------------------------------
# Public exports
# -----------------------------------------------------------------------------
__all__ = [
    "build_where_clause_and_params",
    "build_select_from_search",
    "SelectBuildResult",
]
