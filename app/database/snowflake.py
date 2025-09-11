import os, typing as t

def _load_p8_as_der_bytes(path: str) -> bytes:
    from cryptography.hazmat.primitives import serialization

    with open(path, "rb") as f:
        raw = f.read()
    is_pem = raw.lstrip().startswith(b"-----BEGIN")
    if is_pem:
        key = serialization.load_pem_private_key(raw, password=None)
    else:
        key = serialization.load_der_private_key(raw, password=None)

    # Snowflake needs unencrypted PKCS#8 DER bytes
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

def _describe_view_snowflake(db_path: str) -> dict[str, str]:
    """
    Return {COLUMN_NAME: TYPE_CATEGORY}, where TYPE_CATEGORY in
    {"TEXT","NUMBER","BOOLEAN","DATE","TIMESTAMP","TIME","OTHER"}.
    """
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

def _sf_connect_for(db: str, schema: str, *,
                    oauth_token: str | None = None,
                    role: str | None = None):
    import snowflake.connector

    common = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=db,
        schema=schema,
        client_session_keep_alive=True,
        session_parameters={
            "QUERY_TAG": "api:data-service",
        },
    )

    pk_path = os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]
    pkb = _load_p8_as_der_bytes(pk_path)
    conn = snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        private_key=pkb,
        **common
    )

    return conn

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


def _execute_query_with_conn(db_path: str, sql: str, params, *, role: str | None = None):
    db, schema, _ = _split_db_path(db_path)
    conn = _sf_connect_for(db, schema, oauth_token=None, role=role)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
        return cols, rows
    finally:
        conn.close()
