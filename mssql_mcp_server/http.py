# mssql_mcp_server/http.py
from fastapi import FastAPI, Request
from .server import _handle, _parse_server_and_port, DB_SERVER, DB_DB, ALLOW_TABLES, ALLOW_SCHEMAS, ROW_LIMIT, QUERY_TIMEOUT, _log

app = FastAPI(title="mssql-mcp HTTP")

@app.on_event("startup")
async def startup():
    host, port = _parse_server_and_port(DB_SERVER)
    _log("INFO", "mssql_mcp_server http starting",
         server=f"{host}:{port}", database=DB_DB,
         allow_tables=sorted(list(ALLOW_TABLES)) or None,
         allow_schemas=sorted(list(ALLOW_SCHEMAS)) or None,
         row_limit=ROW_LIMIT, timeout=QUERY_TIMEOUT)

@app.post("/mcp")
async def mcp(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}
    resp = _handle(data)   # <- liefert dict
    return resp            # <- wichtig: dict zurück, NICHT JSONResponse
