from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()

# Disable LangSmith tracing to avoid rate limit errors
import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import os, re, datetime as dt

from copy import deepcopy
from pathlib import Path
from fastapi import Depends, FastAPI, Body, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from typing import Any, List
from decimal import Decimal

from .filters import parse_search_model_json
from .registry import Registry
from .database import _execute_query_with_conn
from .query import build_select_from_search
from .auth import require_roles
from .auth.require import require_auth, require_roles_access
from .routes import router as auth_public
from .ai import router as ai_router
from .tsx import _to_camel, _as_name, _to_pascal, _infer_ts_type_for_column
from .validation import (
    _assert_columns_allowed,
    _assert_sorts_allowed,
    _assert_filters_allowed,
    _cap_page_size,
)

GLOBAL_MAX_PAGE_SIZE = int(os.getenv("GLOBAL_MAX_PAGE_SIZE", "1000"))

app = FastAPI(title="Pytitan Data Service with AI", version="2.0.0")

app.include_router(auth_public)
app.include_router(ai_router)

origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "")
origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

REG = Registry()


def _to_snake(name: str) -> str:
    """
    Convert camelCase string to snake_case.
    Example: 'developmentAreaId' -> 'development_area_id'
    """
    # Insert an underscore before any uppercase letter that follows a lowercase letter
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Insert an underscore before any uppercase letter that follows a lowercase letter or digit
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _convert_camel_to_snake(sm):
    """
    Convert camelCase property names in SearchModel to snake_case.
    """
    from .filters import FilterExpression, FilterCollection
    
    # Convert columns
    converted_columns = [_to_snake(col) for col in sm.columns]
    
    # Convert sort fields
    converted_sort = [_to_snake(sort_field) for sort_field in sm.sort]
    
    # Convert filter expressions recursively
    def convert_filter_collection(fc: FilterCollection) -> FilterCollection:
        converted_expressions = []
        for expr in fc.expressions:
            converted_expr = FilterExpression(
                property_name=_to_snake(expr.property_name),
                operator=expr.operator,
                value=expr.value
            )
            converted_expressions.append(converted_expr)
        
        converted_collections = [convert_filter_collection(c) for c in fc.collections]
        
        return FilterCollection(
            logical_operator=fc.logical_operator,
            collections=converted_collections,
            expressions=converted_expressions
        )
    
    converted_filter = convert_filter_collection(sm.filter)
    
    # Create new SearchModel with converted names
    converted_sm = deepcopy(sm)
    converted_sm.columns = converted_columns
    converted_sm.sort = converted_sort
    converted_sm.filter = converted_filter
    
    return converted_sm


@app.on_event("startup")
def _startup():
    REG.load_views()
    REG.load_cache()


@app.get("/healthz")
def health():
    try:
        from .ai import AIService

        ai_service = AIService()
        ai_schemas = ai_service.get_available_schemas()
        return {
            "ok": True,
            "entities": list(REG.entities_cfg.keys()),
            "ai_schemas": ai_schemas,
            "services": ["data", "ai"],
        }
    except Exception as e:
        return {
            "ok": True,
            "entities": list(REG.entities_cfg.keys()),
            "ai_schemas": [],
            "services": ["data"],
            "ai_error": str(e),
        }


@app.post("/sql", dependencies=[Depends(require_roles_access(["read:data"]))])
def build_query(
    payload: dict = Body(..., description="SearchModel JSON"),
    paramstyle: str = "pyformat",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
    include_count: bool = False,
    is_camel_case: bool = False,
):
    try:
        sm = parse_search_model_json(payload, validate=True)

        # Convert camelCase property names to snake_case if requested
        if is_camel_case:
            sm = _convert_camel_to_snake(sm)

        entry = REG.ensure_entity(sm.entity_name)
        _assert_columns_allowed(sm.entity_name, sm.columns, entry)
        _assert_sorts_allowed(sm.entity_name, sm.sort, entry)
        _assert_filters_allowed(sm.entity_name, sm.filter, entry)
        sm.page_size = _cap_page_size(sm.entity_name, sm.page_size, entry)

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


@app.post("/search", dependencies=[Depends(require_roles_access(["read:data"]))])
def search(
    payload: dict = Body(..., description="SearchModel JSON"),
    paramstyle: str = "pyformat",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
    is_camel_case: bool = False,
    claims: dict = Depends(require_auth),
):
    print("is_camel_case", is_camel_case)
    try:
        sm = parse_search_model_json(payload, validate=True)

        # Convert camelCase property names to snake_case if requested
        if is_camel_case:
            sm = _convert_camel_to_snake(sm)

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

        role = os.getenv("SNOWFLAKE_DEFAULT_ROLE")

        cols, rows = _execute_query_with_conn(
            entry["view"], build.sql, build.params, role=role
        )

        return {
            "columns": cols,
            "rows": rows,
            "sql": build.sql,
            "params": build.params,
            "pageSizeApplied": sm.page_size,
            "mappedView": entry["view"],
            "entity": sm.entity_name,
        }
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(payload)
        raise e
        # raise HTTPException(status_code=400, detail=str(e))


@app.get("/entities", dependencies=[Depends(require_roles_access(["read:data"]))])
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

        if ensure:
            try:
                cached = REG.ensure_entity(name)
            except Exception as e:
                out.append(
                    {
                        "entity": name,
                        "view": meta["view"],
                        "maxPageSize": int(
                            meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)
                        ),
                        "cached": False,
                        "error": str(e),
                    }
                )
                continue

        item = {
            "entity": name,
            "view": meta["view"],
            "maxPageSize": int(meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
            "cached": bool(cached),
        }
        if cached:
            item["loadedAt"] = cached.get("loadedAt")
            if include_columns:
                item["columns"] = [
                    {"name": col, "type": typ}
                    for col, typ in cached.get("columns", {}).items()
                ]

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
def me(claims=Depends(require_auth)):
    return {
        "sub": claims["sub"],
        "email": claims.get("email"),
        "roles": claims.get("roles", []),
    }


@app.post("/tsx", dependencies=[Depends(require_roles_access(["read:data"]))])
def search_typescript(
    payload: dict = Body(..., description="SearchModel JSON"),
    paramstyle: str = "pyformat",
    use_ilike: bool = False,
    quote_identifiers: bool = False,
    distinct: bool = False,
    is_camel_case: bool = False,
    claims: dict = Depends(require_auth),  # ← add this
):
    """
    Returns a TypeScript class definition with camelCase fields that match the query results.
    - Reuses /search for validation, mapping, and SQL generation/execution.
    - Infers property types from the sampled result rows (first page returned by /search).
    - If no non-null samples exist for a column, falls back to `unknown | null`.
    """
    try:
        base = search(
            payload=payload,
            paramstyle=paramstyle,
            use_ilike=use_ilike,
            quote_identifiers=quote_identifiers,
            distinct=distinct,
            is_camel_case=is_camel_case,
            claims=claims,
        )

        cols_raw: List[Any] = base.get("columns", [])
        rows: List[List[Any]] = base.get("rows", [])
        mapped_view: str = base.get("entity", "Result")

        keys = [_to_camel(_as_name(c)) for c in cols_raw]
        keys = [k if k else "col" for k in keys]

        samples_by_col: List[List[Any]] = [[] for _ in keys]
        for r in rows:
            for i in range(min(len(keys), len(r))):
                samples_by_col[i].append(r[i])

        ts_types = [_infer_ts_type_for_column(samples) for samples in samples_by_col]

        class_name = f"{_to_pascal(mapped_view)}"

        props_src = "\n".join(
            [f"  {keys[i]}: {ts_types[i]} | undefined;" for i in range(len(keys))]
        )

        ts = f"""// Auto-generated from /search on {dt.datetime.utcnow().isoformat()}Z
// View: {mapped_view}
export class {class_name} {{
{props_src}

  constructor(init?: Partial<{class_name}>) {{
    Object.assign(this, init);
  }}
}}
"""
        return Response(content=ts, media_type="text/plain")

    except Exception:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/save", dependencies=[Depends(require_roles_access(["read:data"]))])
def save(
    user_id: int = Body(..., description="User ID"),
    object_type: str = Body(..., description="Object type"),
    object_key: str = Body(..., description="Object key"),
    payload: str = Body(..., description="Payload as JSON string"),
    claims: dict = Depends(require_auth),
):
    """
    Save data by calling the SC_FIRE_EVENT stored procedure in Snowflake.
    """
    try:
        print(claims)
        # Prepare the stored procedure call
        sql = "CALL SC_FIRE_EVENT(%(user_id)s, %(object_type)s, %(object_key)s, %(payload)s)"
        params = {
            "user_id": user_id,
            "object_type": object_type,
            "object_key": object_key,
            "payload": payload
        }
        
        role = os.getenv("SNOWFLAKE_DEFAULT_ROLE")
        
        # Execute the stored procedure
        cols, rows = _execute_query_with_conn(
            "SC_FIRE_EVENT", sql, params, role=role
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "object_type": object_type,
            "object_key": object_key,
            "result": rows[0] if rows else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))