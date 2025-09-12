import os

from ..registry import RegistryEntry
from ..filters import FilterCollection, Operator

GLOBAL_MAX_PAGE_SIZE = int(os.getenv("GLOBAL_MAX_PAGE_SIZE", "1000"))
_TEXTY = {"TEXT"}
_NUMERIC = {"NUMBER"}
_DATES = {"DATE", "TIMESTAMP", "TIME"}


def _assert_columns_allowed(entity: str, cols: list[str], reg: RegistryEntry) -> None:
    if not cols or cols == ["*"]:
        return
    allowed = set(reg["columns"].keys())
    for c in cols:
        if c.upper() not in allowed and c != "*":
            raise ValueError(f"Column not allowed for {entity}: {c}")


def _assert_sorts_allowed(entity: str, sorts: list[str], reg: RegistryEntry) -> None:
    allowed = set(reg["columns"].keys())
    for s in sorts or []:
        s = s.strip()
        if not s:
            continue
        col = s[1:] if s.startswith("-") else s.split(":")[0].split()[0]
        if col.upper() not in allowed:
            raise ValueError(f"Sort field not allowed for {entity}: {col}")


def _assert_filters_allowed(
    entity: str, fc: FilterCollection, reg: RegistryEntry
) -> None:
    allowed = reg["columns"]

    def walk(node: FilterCollection):
        for e in node.expressions:
            col = e.property_name.upper()
            if col not in allowed:
                raise ValueError(
                    f"Filter column not allowed for {entity}: {e.property_name}"
                )
            typ = allowed[col]
            if (
                e.operator in (Operator.LK, Operator.SW, Operator.EW)
                and typ not in _TEXTY
            ):
                raise ValueError(
                    f"Operator {e.operator.value} not allowed on non-text column {e.property_name}"
                )
            if e.operator in (
                Operator.GT,
                Operator.GTE,
                Operator.LT,
                Operator.LTE,
            ) and typ not in (_NUMERIC | _DATES):
                raise ValueError(
                    f"Operator {e.operator.value} not allowed on column {e.property_name} of type {typ}"
                )
        for c in node.collections:
            walk(c)

    walk(fc)


def _cap_page_size(entity: str, page_size: int, reg: RegistryEntry) -> int:
    cap = int(reg.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE))
    if page_size <= 0:
        return min(100, cap)  # nice default
    return min(page_size, cap)
