from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json, os, time, typing as t
from copy import deepcopy
from pathlib import Path
from fastapi import Depends, FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import yaml

from .myfilter import (
    parse_search_model_json,
    FilterCollection, FilterExpression, Operator,  # for validation
)
from .myquery import build_select_from_search
from .google_oidc import verify_google_id_token, require_roles

VIEWS_PATH = Path(os.getenv("VIEWS_FILE", "config/views.yaml"))
CACHE_PATH = Path(os.getenv("COLUMNS_CACHE_FILE", "config/columns_cache.json"))
GLOBAL_MAX_PAGE_SIZE = int(os.getenv("GLOBAL_MAX_PAGE_SIZE", "1000"))
SF_ENABLED = os.getenv("SNOWFLAKE_ENABLED", "false").lower() == "true"

def _split_db_path(path: str) -> tuple[str, str, str]:
    """Accept 1-, 2-, or 3-part names; fill missing parts from env."""
    parts = [p.strip().strip('"') for p in path.split(".") if p.strip() != ""]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        db = os.environ.get("SNOWFLAKE_DATABASE")
        if not db:
            raise RuntimeError("SCHEMA.VIEW given but SNOWFLAKE_DATABASE not set.")
        return db, parts[0], parts[1]
    if len(parts) == 1:
        db = os.environ.get("SNOWFLAKE_DATABASE")
        schema = os.environ.get("SNOWFLAKE_SCHEMA")
        if not db or not schema:
            raise RuntimeError("VIEW given but SNOWFLAKE_DATABASE or SNOWFLAKE_SCHEMA missing.")
        return db, schema, parts[0]
    raise RuntimeError(f"Invalid object name: {path!r}")

def _sf_connect_for(db: str, schema: str):
    import snowflake.connector  # lazy import
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=db,
        schema=schema,
        role=os.getenv("SNOWFLAKE_ROLE"),
    )

def _describe_view_snowflake(db_path: str) -> dict[str, str]:
    """
    Return {COLUMN_NAME: TYPE_CATEGORY}, where TYPE_CATEGORY in
    {"TEXT","NUMBER","BOOLEAN","DATE","TIMESTAMP","TIME","OTHER"}.
    """
    if not SF_ENABLED:
        raise RuntimeError("Snowflake discovery disabled (set SNOWFLAKE_ENABLED=true).")
    db, schema, view = _split_db_path(db_path)
    conn = _sf_connect_for(db, schema)
    try:
        sql = f"""
        SELECT COLUMN_NAME, DATA_TYPE
        FROM {db.upper()}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """
        with conn.cursor() as cur:
            cur.execute(sql, (schema.upper(), view.upper()))
            rows = cur.fetchall()

        def bucket(dtype: str) -> str:
            u = dtype.upper()
            if any(x in u for x in ("CHAR", "TEXT", "STRING", "BINARY")): return "TEXT"
            if any(x in u for x in ("NUMBER", "DECIMAL", "INT", "FLOAT", "DOUBLE")): return "NUMBER"
            if "BOOLEAN" in u: return "BOOLEAN"
            if "TIMESTAMP" in u: return "TIMESTAMP"
            if u == "DATE": return "DATE"
            if u == "TIME": return "TIME"
            return "OTHER"

        return {name: bucket(dtype) for (name, dtype) in rows}
    finally:
        conn.close()

def _execute_query(db_path: str, sql: str, params) -> tuple[list[str], list[tuple]]:
    """Execute SQL against Snowflake and return (columns, rows)."""
    if not SF_ENABLED:
        raise RuntimeError("Execution disabled (set SNOWFLAKE_ENABLED=true).")
    db, schema, _ = _split_db_path(db_path)
    conn = _sf_connect_for(db, schema)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
        return cols, rows
    finally:
        conn.close()

# --------------------------- Registry -----------------------------
class EntityMeta(t.TypedDict, total=False):
    view: str
    maxPageSize: int

class RegistryEntry(t.TypedDict):
    view: str
    columns: dict[str, str]  # NAME -> TYPE_CATEGORY
    loadedAt: str
    maxPageSize: int

class Registry:
    def __init__(self):
        self.entities_cfg: dict[str, EntityMeta] = {}
        self.columns_cache: dict[str, RegistryEntry] = {}

    def load_views(self) -> None:
        if not VIEWS_PATH.exists():
            raise RuntimeError(f"View mapping file not found: {VIEWS_PATH}")
        with VIEWS_PATH.open("r", encoding="utf-8") as f:
            if VIEWS_PATH.suffix.lower() in (".yaml", ".yml"):
                if not yaml:
                    raise RuntimeError("PyYAML not installed but a YAML views file was provided.")
                cfg = yaml.safe_load(f)
            else:
                cfg = json.load(f)
        ents = cfg.get("entities", {})
        norm: dict[str, EntityMeta] = {}
        for k, v in ents.items():
            if not isinstance(v, dict) or "view" not in v:
                raise RuntimeError(f"Bad entity mapping for {k}: {v}")
            item: EntityMeta = {"view": v["view"]}
            if "maxPageSize" in v:
                item["maxPageSize"] = int(v["maxPageSize"])
            norm[k] = item
        self.entities_cfg = norm

    def load_cache(self) -> None:
        if CACHE_PATH.exists():
            with CACHE_PATH.open("r", encoding="utf-8") as f:
                self.columns_cache = json.load(f)
        else:
            self.columns_cache = {}

    def save_cache(self) -> None:
        tmp = CACHE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.columns_cache, f, indent=2)
        tmp.replace(CACHE_PATH)

    def ensure_entity(self, name: str) -> RegistryEntry:
        if name not in self.entities_cfg:
            raise KeyError(f"Unknown entity: {name}")
        cfg = self.entities_cfg[name]
        cached = self.columns_cache.get(name)
        if cached and cached.get("view") == cfg["view"]:
            return cached
        cols = _describe_view_snowflake(cfg["view"])
        entry: RegistryEntry = {
            "view": cfg["view"],
            "columns": cols,
            "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "maxPageSize": int(cfg.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
        }
        self.columns_cache[name] = entry
        self.save_cache()
        return entry

    def refresh_all(self) -> dict[str, str]:
        """Re-read views file and re-discover all entities."""
        self.load_views()
        summaries: dict[str, str] = {}
        for name, meta in self.entities_cfg.items():
            try:
                cols = _describe_view_snowflake(meta["view"])
                self.columns_cache[name] = {
                    "view": meta["view"],
                    "columns": cols,
                    "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "maxPageSize": int(meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
                }
                summaries[name] = f"ok ({len(cols)} cols)"
            except Exception as e:
                summaries[name] = f"error: {e}"
        self.save_cache()
        return summaries

# ---------------------- Validation helpers -------------------------
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

def _assert_filters_allowed(entity: str, fc: FilterCollection, reg: RegistryEntry) -> None:
    allowed = reg["columns"]
    def walk(node: FilterCollection):
        for e in node.expressions:
            col = e.property_name.upper()
            if col not in allowed:
                raise ValueError(f"Filter column not allowed for {entity}: {e.property_name}")
            typ = allowed[col]
            if e.operator in (Operator.LK, Operator.SW, Operator.EW) and typ not in _TEXTY:
                raise ValueError(f"Operator {e.operator.value} not allowed on non-text column {e.property_name}")
            if e.operator in (Operator.GT, Operator.GTE, Operator.LT, Operator.LTE) and typ not in (_NUMERIC | _DATES):
                raise ValueError(f"Operator {e.operator.value} not allowed on column {e.property_name} of type {typ}")
        for c in node.collections:
            walk(c)
    walk(fc)

def _cap_page_size(entity: str, page_size: int, reg: RegistryEntry) -> int:
    cap = int(reg.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE))
    if page_size <= 0:
        return min(100, cap)  # nice default
    return min(page_size, cap)

# --------------------------- FastAPI app ----------------------------
app = FastAPI(title="QueryBuilder Service", version="1.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REG = Registry()

@app.on_event("startup")
def _startup():
    REG.load_views()
    REG.load_cache()

@app.get("/healthz")
def health():
    return {"ok": True, "entities": list(REG.entities_cfg.keys())}

@app.post("/sql", dependencies=[Depends(require_roles(["read:data"]))])
def build_query(
    payload: dict = Body(..., description="SearchModel in camelCase JSON"),
    paramstyle: str = "pyformat",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
    include_count: bool = False,
):
    try:
        sm = parse_search_model_json(payload, validate=True)

        # Resolve entity → view and validate against registry
        entry = REG.ensure_entity(sm.entity_name)
        _assert_columns_allowed(sm.entity_name, sm.columns, entry)
        _assert_sorts_allowed(sm.entity_name, sm.sort, entry)
        _assert_filters_allowed(sm.entity_name, sm.filter, entry)
        sm.page_size = _cap_page_size(sm.entity_name, sm.page_size, entry)

        # IMPORTANT: map to DB view BEFORE building SQL (QueryBuilder sees only DB names)
        sm_for_sql = deepcopy(sm)
        sm_for_sql.entity_name = entry["view"]

        res = build_select_from_search(
            sm_for_sql,
            paramstyle=paramstyle,
            use_ilike=use_ilike,
            quote_identifiers=quote_identifiers,
            distinct=distinct,
            include_count=include_count,
        )
        return {
            "sql": res.sql,
            "params": res.params,
            "countSql": res.count_sql,
            "countParams": res.count_params,
            "pageSizeApplied": sm.page_size,
            "maxPageSize": entry.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE),
            "mappedView": entry["view"],
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/search", dependencies=[Depends(require_roles(["read:data"]))])
def search(
    payload: dict = Body(..., description="SearchModel in camelCase JSON"),
    paramstyle: str = "pyformat",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
):
    if not SF_ENABLED:
        raise HTTPException(status_code=501, detail="Execution disabled; set SNOWFLAKE_ENABLED=true to enable /search.")
    try:
        sm = parse_search_model_json(payload, validate=True)
        entry = REG.ensure_entity(sm.entity_name)
        _assert_columns_allowed(sm.entity_name, sm.columns, entry)
        _assert_sorts_allowed(sm.entity_name, sm.sort, entry)
        _assert_filters_allowed(sm.entity_name, sm.filter, entry)
        sm.page_size = _cap_page_size(sm.entity_name, sm.page_size, entry)

        sm_for_sql = deepcopy(sm)
        sm_for_sql.entity_name = entry["view"]

        build = build_select_from_search(
            sm_for_sql,
            paramstyle=paramstyle,
            use_ilike=use_ilike,
            quote_identifiers=quote_identifiers,
            distinct=distinct,
            include_count=False,
        )
        cols, rows = _execute_query(entry["view"], build.sql, build.params)

        return {
            "columns": cols,
            "rows": rows,
            "sql": build.sql,
            "params": build.params,
            "pageSizeApplied": sm.page_size,
            "mappedView": entry["view"],
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/entities", dependencies=[Depends(require_roles(["read:data"]))])
def list_entities(
    include_columns: bool = True,
    ensure: bool = False,
):
    """
    List configured entities and (optionally) their column/type info.

    - include_columns: if True, returns columns when present in cache.
    - ensure: if True, attempts to ensure column metadata for each entity by
      calling REG.ensure_entity(...) which may query Snowflake (requires SNOWFLAKE_ENABLED=true).
    """
    out = []
    for name, meta in REG.entities_cfg.items():
        cached = REG.columns_cache.get(name)

        # Optionally ensure discovery (fills cache if missing/outdated)
        if ensure:
            try:
                cached = REG.ensure_entity(name)
            except Exception as e:
                # If discovery fails (e.g., SF disabled), keep going and report the error
                out.append({
                    "entity": name,
                    "view": meta["view"],
                    "maxPageSize": int(meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
                    "cached": False,
                    "error": str(e),
                })
                continue  # next entity

        item = {
            "entity": name,
            "view": meta["view"],
            "maxPageSize": int(meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
            "cached": bool(cached),
        }
        if cached:
            item["loadedAt"] = cached.get("loadedAt")
            if include_columns:
                # columns as [{name, type}] for friendlier JSON
                item["columns"] = [
                    {"name": col, "type": typ} for col, typ in cached.get("columns", {}).items()
                ]
                # Or, if you prefer the raw dict, swap the above with:
                # item["columns"] = cached.get("columns", {})
        out.append(item)

    return {"entities": out}

@app.post("/reload", dependencies=[Depends(require_roles(["admin"]))])
def reload_registry():
    try:
        summary = REG.refresh_all()
        return {"reloaded": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/me")
def me(claims = Depends(verify_google_id_token)):
    return {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "name": claims.get("name"),
    }
