import os, sys, json, re, time, uuid, traceback, base64, decimal, datetime
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel
from dotenv import load_dotenv

# ---- Konfiguration über ENV ----
load_dotenv()

DB_SERVER  = os.getenv("MSSQL_SERVER", "127.0.0.1,1433")
DB_DB      = os.getenv("MSSQL_DATABASE", "")
DB_USER    = os.getenv("MSSQL_USER", "")
DB_PASS    = os.getenv("MSSQL_PASSWORD", "")
DB_ENCRYPT = os.getenv("MSSQL_ENCRYPT", "false").lower() == "true"
DB_TSC     = os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", "true").lower() == "true"

ALLOW_TABLES   = set(filter(None, [t.strip() for t in os.getenv("ALLOW_TABLES", "").split(",")]))
ALLOW_SCHEMAS  = set(filter(None, [s.strip() for s in os.getenv("ALLOW_SCHEMAS", "").split(",")]))
DENY_COLUMNS   = [c.strip() for c in os.getenv("DENY_COLUMNS", "").split(",") if c.strip()]   # z.B. "dbo.Customers.SSN,*.Password"
DENY_PATTERNS  = [p for p in os.getenv("DENY_PATTERNS", "").split("|") if p]                  # Regex-Barrieren

ROW_LIMIT     = int(os.getenv("ROW_LIMIT", "500"))
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT", "10"))  # Sekunden
BINARY_MODE   = os.getenv("BINARY_MODE", "placeholder")  # "placeholder" | "base64" | "hex"
BINARY_MAX    = int(os.getenv("BINARY_MAX", "65536"))    # max Bytes encodieren

LOG = os.getenv("LOG_LEVEL", "INFO").upper()

# ---- DB (pymssql) ----
import pymssql


def _parse_server_and_port(server_str: str) -> Tuple[str, int]:
    s = server_str.strip()
    port = 1433
    host = s
    if "," in s:
        host, p = s.rsplit(",", 1); port = int(p)
    elif ":" in s and s.count(":") == 1:
        host, p = s.rsplit(":", 1); port = int(p)
    return host.strip(), port


def _connect():
    host, port = _parse_server_and_port(DB_SERVER)
    return pymssql.connect(
        server=host, port=port,
        user=DB_USER, password=DB_PASS, database=DB_DB,
        login_timeout=QUERY_TIMEOUT, timeout=QUERY_TIMEOUT,
        as_dict=False, tds_version='7.4', appname='mssql_mcp'
    )

# ---- Guards & RBAC ----
_select_only = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
_banned_kw   = re.compile(r"\b(insert|update|delete|drop|alter|truncate|exec|merge|create)\b", re.IGNORECASE)
_offset_pat  = re.compile(r"\boffset\s+\d+\s+rows\b", re.IGNORECASE)
_fetch_pat   = re.compile(r"\bfetch\s+next\s+\d+\s+rows\s+only\b", re.IGNORECASE)
_top_pat     = re.compile(r"\btop\s+\d+\b", re.IGNORECASE)

_DENY_PATTERNS_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in DENY_PATTERNS]

def ensure_safe_sql(sql: str):
    s = sql.strip()
    if not _select_only.match(s): raise ValueError("Nur SELECT-Statements sind erlaubt.")
    if ";" in s: raise ValueError("Nur ein einzelnes Statement ohne ';' ist erlaubt.")
    if _banned_kw.search(s): raise ValueError("Nur lesender Zugriff: DDL/DML/EXEC sind verboten.")
    for rx in _DENY_PATTERNS_RE:
        if rx.search(s): raise ValueError("Query verletzt eine gesperrte Muster-Regel (DENY_PATTERNS).")
    _block_denied_columns_in_sql(s)

def ensure_table_allowed(table: str):
    # Whitelist Tabellen
    if ALLOW_TABLES:
        t = table.strip("[]")
        if t in ALLOW_TABLES: pass
        elif "." not in t and f"dbo.{t}" in ALLOW_TABLES: pass
        else: raise ValueError(f"Tabelle '{table}' ist nicht freigegeben.")
    # Whitelist Schemas
    if ALLOW_SCHEMAS:
        # akzeptiere schema.name oder nur name -> dann dbo
        schema, dot, name = table.partition(".")
        if not dot: schema = "dbo"
        if schema.strip("[]") not in ALLOW_SCHEMAS:
            raise ValueError(f"Schema '{schema}' ist nicht freigegeben.")

def _block_denied_columns_in_sql(sql: str):
    """
    Simple Heuristik: blockiert, wenn DENY_COLUMNS-Namen im SQL auftauchen.
    Unterstützt:
      - 'schema.table.column'
      - '*.column' (alle Tabellen)
      - 'column' (global, vorsichtig)
    """
    if not DENY_COLUMNS: return
    lowered = sql.lower()
    for spec in DENY_COLUMNS:
        s = spec.strip()
        if not s: continue
        parts = s.lower().split(".")
        # baue ein robustes Wortgrenzen-Muster
        if len(parts) == 3:   # schema.table.column
            schema, table, col = parts
            pat = rf"\b{re.escape(schema)}\s*\.?\s*{re.escape(table)}\s*\.?\s*{re.escape(col)}\b"
        elif len(parts) == 2: # table.column oder *.column
            t, col = parts
            if t == "*":
                pat = rf"\b{re.escape(col)}\b"
            else:
                pat = rf"\b{re.escape(t)}\s*\.?\s*{re.escape(col)}\b"
        else:                 # nur column
            col = parts[0]
            pat = rf"\b{re.escape(col)}\b"
        if re.search(pat, lowered, re.IGNORECASE):
            raise ValueError(f"Verbotene Spalte referenziert: '{spec}' (DENY_COLUMNS).")

# ---- Quoting-Helper ----
def _quote_ident(table: str) -> str:
    t = table.strip().strip("[]")
    parts = t.split(".")
    safe = []
    for p in parts:
        p = p.strip().strip("[]").replace("]", "]]")
        safe.append(f"[{p}]")
    return ".".join(safe) if safe else t

# ---- JSON-Safe Encoder ----
def _jsonify_value(v: Any) -> Any:
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        if BINARY_MODE == "base64":
            chunk = b[:BINARY_MAX]; enc = base64.b64encode(chunk).decode("ascii")
            return {"__binary__":"base64","len":len(b),"data":enc,"truncated":len(b)>len(chunk)}
        elif BINARY_MODE == "hex":
            chunk = b[:BINARY_MAX]; enc = chunk.hex()
            return {"__binary__":"hex","len":len(b),"data":enc,"truncated":len(b)>len(chunk)}
        else:
            return f"[[BINARY {len(b)} bytes]]"
    if isinstance(v, decimal.Decimal): return str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)): return v.isoformat()
    if isinstance(v, uuid.UUID): return str(v)
    return v

def _jsonify_row(cols: List[str], row_tuple: Tuple[Any, ...]) -> Dict[str, Any]:
    return {col: _jsonify_value(val) for col, val in zip(cols, row_tuple)}

# ---- Modelle ----
class QueryResult(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    truncated: bool
    execution_ms: int

# ---- Tools ----
def tool_tables() -> List[str]:
    if ALLOW_TABLES: return sorted(ALLOW_TABLES)
    with _connect() as c:
        cur = c.cursor()
        cur.execute("""
            SELECT CONCAT(TABLE_SCHEMA, '.', TABLE_NAME)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE='BASE TABLE'
            ORDER BY 1
        """)
        return [r[0] for r in cur.fetchall()]

def tool_columns(table: str) -> List[Dict[str, Any]]:
    ensure_table_allowed(table)
    schema, dot, name = table.partition(".")
    if not dot: schema, name = "dbo", schema
    with _connect() as c:
        cur = c.cursor(as_dict=True)
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            ORDER BY ORDINAL_POSITION
        """, (schema, name))
        return [{
            "column": r["COLUMN_NAME"],
            "type": r["DATA_TYPE"],
            "nullable": (r["IS_NULLABLE"] == "YES"),
            "max_len": r["CHARACTER_MAXIMUM_LENGTH"],
            "position": r["ORDINAL_POSITION"],
        } for r in cur.fetchall()]

def _apply_top_limit(sql: str) -> str:
    # Kein TOP injizieren, wenn bereits paginiert
    if _offset_pat.search(sql) or _fetch_pat.search(sql): return sql
    if _top_pat.search(sql): return sql
    return re.sub(r"^\s*select\b", f"SELECT TOP {ROW_LIMIT}", sql, flags=re.IGNORECASE)

def tool_query(sql: str) -> QueryResult:
    ensure_safe_sql(sql)
    sql_eff = _apply_top_limit(sql.strip())
    t0 = time.time()
    with _connect() as c:
        c.cursor().execute(f"SET LOCK_TIMEOUT {QUERY_TIMEOUT * 1000};")
        cur = c.cursor()
        cur.execute(sql_eff)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    ms = int((time.time() - t0) * 1000)
    dict_rows = [_jsonify_row(cols, r) for r in rows]
    truncated = len(dict_rows) >= ROW_LIMIT
    return QueryResult(columns=cols, rows=dict_rows, row_count=len(dict_rows), truncated=truncated, execution_ms=ms)

def tool_sample(table: str, n: int = 50) -> QueryResult:
    ensure_table_allowed(table)
    n = max(1, min(n, ROW_LIMIT))
    qname = _quote_ident(table)
    sql = f"SELECT TOP {n} * FROM {qname}"
    return tool_query(sql)

def tool_paginate(sql: str, offset: int = 0, fetch: int = 100) -> QueryResult:
    ensure_safe_sql(sql)
    fetch = max(1, min(fetch, ROW_LIMIT))
    if re.search(r"\border\s+by\b", sql, re.IGNORECASE) is None:
        sql = f"{sql.rstrip()} ORDER BY 1"
    paged = f"{sql} OFFSET {max(0, offset)} ROWS FETCH NEXT {fetch} ROWS ONLY"
    return tool_query(paged)

def tool_stats(table: str, sample_n: int = 5) -> Dict[str, Any]:
    ensure_table_allowed(table)
    qname = _quote_ident(table)
    with _connect() as c:
        cur = c.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {qname}")
        total = cur.fetchone()[0]
    sample = tool_sample(table, sample_n).model_dump()
    return {"table": table, "row_count": total, "sample": sample}

def tool_columns_with_examples(table: str, n: int = 5) -> Dict[str, Any]:
    """
    Spalten-Metadaten + bis zu n Beispielwerte je Spalte.
    - Überspringt BLOB-Spalten (image/varbinary) oder gibt Platzhalter aus.
    - Für (n)var/char nutzt DISTINCT + IS NOT NULL.
    - Für numerische/zeitliche Felder ebenfalls DISTINCT; NULLs werden übersprungen.
    """
    ensure_table_allowed(table)
    n = max(1, n)
    meta = tool_columns(table)
    qname = _quote_ident(table)

    examples: Dict[str, List[Any]] = {}
    with _connect() as c:
        for m in meta:
            col = m["column"]
            dtype = (m["type"] or "").lower()
            col_q = f"[{col.replace(']', ']]')}]"

            # BLOBs überspringen – nur Marker ausgeben
            if dtype in ("image", "varbinary", "binary"):
                examples[col] = ["[[BINARY]]"]
                continue

            # Für textuelle & sonstige Typen DISTINCT Top n, NULLs raus
            stmt = f"SELECT TOP {n} DISTINCT {col_q} FROM {qname} WHERE {col_q} IS NOT NULL"

            # Bei TEXT/NTEXT/TEXTLIKE: DISTINCT kann manchmal stören -> fallback ohne DISTINCT
            if dtype in ("text", "ntext"):
                stmt = f"SELECT TOP {n} {col_q} FROM {qname} WHERE {col_q} IS NOT NULL"

            try:
                cur = c.cursor()
                cur.execute(stmt)
                rows = [r[0] for r in cur.fetchall()]
                # JSON-safe konvertieren
                examples[col] = [_jsonify_value(v) for v in rows]
            except Exception as ex:
                # Als Fallback noch eine ganz simple Variante probieren
                try:
                    cur = c.cursor()
                    fallback = f"SELECT TOP {n} {col_q} FROM {qname}"
                    cur.execute(fallback)
                    rows = [r[0] for r in cur.fetchall()]
                    examples[col] = [_jsonify_value(v) for v in rows]
                except Exception:
                    # Wenn auch das scheitert: leere Liste (aber nicht alles leise „verschlucken“)
                    _log("ERROR", "examples_failed", column=col, dtype=dtype, stmt=stmt, table=table)
                    examples[col] = []

    return {"table": table, "columns": meta, "examples": examples}

def tool_explain(sql: str) -> Dict[str, Any]:
    """
    Heuristische Analyse der Query (kein echter Optimizer-Plan).
    Meldet potentielle Risiken + Empfehlungen.
    """
    s = sql.strip()
    issues: List[Dict[str, Any]] = []
    tips: List[str] = []

    # Guard-Auswertung
    try:
        ensure_safe_sql(s)
    except Exception as e:
        issues.append({"type": "safety", "message": str(e), "severity": "error"})

    low = s.lower()

    # SELECT *?
    if re.search(r"select\s+\*", low):
        issues.append({"type": "projection", "message": "SELECT * kann unnötig viele Spalten ziehen.", "severity": "warn"})
        tips.append("Nur benötigte Spalten selektieren.")

    # WHERE vorhanden?
    if " where " not in f" {low} ":
        issues.append({"type": "filter", "message": "Kein WHERE-Filter – kann zu Full Table Scan führen.", "severity": "warn"})
        tips.append("Mit WHERE filtern (z. B. Datum/ID).")

    # ORDER BY + Pagination
    has_order = re.search(r"\border\s+by\b", low) is not None
    has_offset = _offset_pat.search(low) is not None or _fetch_pat.search(low) is not None
    if has_offset and not has_order:
        issues.append({"type": "order", "message": "OFFSET/FETCH ohne ORDER BY ist nondeterministisch.", "severity": "error"})
        tips.append("ORDER BY definieren, bevor OFFSET/FETCH genutzt wird.")
    if not has_offset and not has_order:
        tips.append("Für stabile Reihenfolge ORDER BY setzen.")
    if has_offset:
        tips.append("Bei großen Ergebnismengen OFFSET/FETCH mit selektivem WHERE kombinieren.")

    # Mögliche CROSS JOINs / fehlende Join-Bedingungen (heuristisch)
    if " join " in low and " on " not in low:
        issues.append({"type": "join", "message": "JOIN ohne ON-Bedingung erkannt (möglicher Kreuzprodukt).", "severity": "warn"})
        tips.append("JOIN ... ON <Schlüssel> hinzufügen.")
    if re.search(r"\bfrom\b[^;]+,([^;]+)", low):
        issues.append({"type": "join", "message": "Kommagetrennte FROM-Liste – prüfen auf Kreuzprodukt.", "severity": "info"})
        tips.append("Explizite JOIN-Syntax mit ON verwenden.")

    # Verbotene Spalten?
    try:
        _block_denied_columns_in_sql(s)
    except Exception as e:
        issues.append({"type": "rbac", "message": str(e), "severity": "error"})

    # TOP + OFFSET Konflikt?
    if _top_pat.search(low) and (_offset_pat.search(low) or _fetch_pat.search(low)):
        issues.append({"type": "pagination", "message": "TOP und OFFSET/FETCH in derselben Query sind inkompatibel.", "severity": "error"})
        tips.append("Entweder TOP oder OFFSET/FETCH verwenden, nicht beides.")

    return {
        "ok": len([i for i in issues if i.get("severity") == "error"]) == 0,
        "issues": issues,
        "suggestions": list(dict.fromkeys(tips))  # eindeutige Reihenfolge
    }

# ---- STDIO Loop ----
def _log(level: str, msg: str, **kw):
    if level == "DEBUG" and LOG not in ("DEBUG",): return
    entry = {"ts": time.time(), "level": level, "msg": msg, **kw}
    print(json.dumps({"log": entry}), flush=True, file=sys.stderr)

def _handle(req: Dict[str, Any]) -> Dict[str, Any]:
    rid = req.get("id") or str(uuid.uuid4())
    action = (req.get("action") or "").lower()
    try:
        if action == "ping":
            return {"id": rid, "ok": True, "result": "pong"}
        if action == "tools":
            return {"id": rid, "ok": True, "result": {"tools": [
                {"name": "tables",   "params": {}},
                {"name": "columns",  "params": {"table": "str"}},
                {"name": "columns_with_examples", "params": {"table": "str", "n": "int (optional)"}},
                {"name": "query",    "params": {"sql": "str"}},
                {"name": "sample",   "params": {"table": "str", "n": "int (optional)"}},
                {"name": "paginate", "params": {"sql": "str", "offset": "int", "fetch": "int"}},
                {"name": "stats",    "params": {"table": "str", "sample_n": "int (optional)"}},
                {"name": "explain",  "params": {"sql": "str"}},
            ]}}
        if action == "tables":
            return {"id": rid, "ok": True, "result": tool_tables()}
        if action == "columns":
            table = req.get("table");  assert table, "Parameter 'table' fehlt."
            return {"id": rid, "ok": True, "result": tool_columns(table)}
        if action == "columns_with_examples":
            table = req.get("table");  assert table, "Parameter 'table' fehlt."
            n = int(req.get("n", 5))
            return {"id": rid, "ok": True, "result": tool_columns_with_examples(table, n)}
        if action == "query":
            sql = req.get("sql");      assert sql, "Parameter 'sql' fehlt."
            res = tool_query(sql).model_dump()
            return {"id": rid, "ok": True, "result": res}
        if action == "sample":
            table = req.get("table");  assert table, "Parameter 'table' fehlt."
            n = int(req.get("n", 50))
            res = tool_sample(table, n).model_dump()
            return {"id": rid, "ok": True, "result": res}
        if action == "paginate":
            sql = req.get("sql");      assert sql, "Parameter 'sql' fehlt."
            offset = int(req.get("offset", 0))
            fetch  = int(req.get("fetch", 100))
            res = tool_paginate(sql, offset, fetch).model_dump()
            return {"id": rid, "ok": True, "result": res}
        if action == "stats":
            table = req.get("table");  assert table, "Parameter 'table' fehlt."
            sample_n = int(req.get("sample_n", 5))
            res = tool_stats(table, sample_n)
            return {"id": rid, "ok": True, "result": res}
        if action == "explain":
            sql = req.get("sql");      assert sql, "Parameter 'sql' fehlt."
            return {"id": rid, "ok": True, "result": tool_explain(sql)}
        raise ValueError(f"Unbekannte action: '{action}'")
    except Exception as e:
        _log("ERROR", "request_failed", action=action, error=str(e), tb=traceback.format_exc())
        return {"id": rid, "ok": False, "error": str(e)}

def run_stdio():
    host, port = _parse_server_and_port(DB_SERVER)
    _log("INFO", "mssql_mcp_server starting",
         server=f"{host}:{port}", database=DB_DB,
         allow_tables=sorted(list(ALLOW_TABLES)) or None,
         allow_schemas=sorted(list(ALLOW_SCHEMAS)) or None,
         row_limit=ROW_LIMIT, timeout=QUERY_TIMEOUT,
         deny_columns=DENY_COLUMNS or None,
         deny_patterns=DENY_PATTERNS or None)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            req = json.loads(line)
        except Exception:
            print(json.dumps({"ok": False, "error": "invalid_json"}), flush=True)
            continue
        resp = _handle(req)
        print(json.dumps(resp), flush=True)
