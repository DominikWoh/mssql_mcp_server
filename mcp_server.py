#!/usr/bin/env python3
"""
MCP-kompatibler STDIO-Server für LM Studio, Jan & OpenWebUI.
- STDOUT: nur JSON-RPC
- STDERR: alle Logs
- Notifications (ohne id) werden NICHT beantwortet.
"""

import sys
import os
import json
import logging
from dotenv import load_dotenv

# ===== Env & Logging =====
load_dotenv()
logging.basicConfig(
    stream=sys.stderr,
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("NO_COLOR", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

# ===== Tool-Implementierungen =====
from mssql_mcp_server.server import (
    tool_tables,
    tool_columns,
    tool_query,
    tool_sample,
    tool_stats,
    tool_explain,
    # (tool_paginate, tool_columns_with_examples optional)
)


class MCPServer:
    def _tools_spec(self):
        return [
            {
                "name": "tables",
                "description": "List all available tables",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "columns",
                "description": "Get column information for a table",
                "inputSchema": {
                    "type": "object",
                    "properties": {"table": {"type": "string"}},
                    "required": ["table"],
                },
            },
            {
                "name": "query",
                "description": "Execute a SQL query",
                "inputSchema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            },
            {
                "name": "sample",
                "description": "Get sample data from a table",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "n": {"type": "integer", "default": 50},
                    },
                    "required": ["table"],
                },
            },
            {
                "name": "stats",
                "description": "Get table statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "sample_n": {"type": "integer", "default": 5},
                    },
                    "required": ["table"],
                },
            },
            {
                "name": "explain",
                "description": "Explain a SQL query",
                "inputSchema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            },
        ]

    def handle_request(self, request: dict):
        """
        Verarbeitet JSON-RPC *Requests* (mit id).
        Notifications ohne id werden außerhalb abgefangen.
        """
        try:
            method = request.get("method")
            params = request.get("params", {}) or {}
            req_id = request.get("id")

            logging.info("mcp_request method=%s params=%s id=%s", method, params, req_id)

            # ---- Handshake / Capabilities ----
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "mssql-mcp-server", "version": "1.0.0"},
                    },
                }

            if method == "capabilities/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"capabilities": {"tools": {}}},
                }

            # No-Op Ping (falls Client *mit* id pingt)
            if method in ("ping", "notifications/ping"):
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}

            # ---- Tools auflisten ----
            if method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": self._tools_spec()},
                }

            # ---- Tools ausführen ----
            if method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {}) or {}
                logging.info("tool_call name=%s args=%s", tool_name, tool_args)

                if tool_name == "tables":
                    result = tool_tables()
                    text = f"Available tables ({len(result)}):\n" + "\n".join(result)

                elif tool_name == "columns":
                    tbl = tool_args["table"]
                    cols = tool_columns(tbl)
                    parts = []
                    for col in cols:
                        s = f"{col['column']}:{col['type']}"
                        if col.get("max_len"):
                            s += f"({col['max_len']})"
                        if col.get("nullable"):
                            s += "?"
                        parts.append(s)
                    text = f"Columns for '{tbl}' ({len(cols)}): " + " | ".join(parts)

                elif tool_name == "query":
                    res = tool_query(tool_args["sql"])
                    text = f"Query executed: {res.row_count} rows"
                    if getattr(res, "truncated", False):
                        text += " (truncated)"
                    text += f" in {res.execution_ms}ms\n\n"
                    if res.rows:
                        text += "Results:\n"
                        for i, row in enumerate(res.rows):
                            text += f"Row {i+1}: {dict(list(row.items())[:3])}\n"

                elif tool_name == "sample":
                    n = int(tool_args.get("n", 50))
                    tbl = tool_args["table"]
                    res = tool_sample(tbl, n)
                    sample_size = min(len(res.rows or []), n)
                    text = f"Sample from '{tbl}': {sample_size} rows"
                    if getattr(res, "truncated", False):
                        text += " (truncated)"
                    text += f" (total: {res.row_count})\n\n"
                    if res.rows:
                        text += "Sample data:\n"
                        for i, row in enumerate(res.rows):
                            text += f"Row {i+1}: {dict(list(row.items())[:2])}\n"

                elif tool_name == "stats":
                    tbl = tool_args["table"]
                    res = tool_stats(tbl, int(tool_args.get("sample_n", 5)))
                    text = f"Table '{tbl}' statistics:\n"
                    text += f"Total rows: {res['row_count']}\n"
                    text += f"Sample rows: {len(res['sample']['rows'])}\n\n"
                    for i, row in enumerate(res["sample"]["rows"][:3]):
                        text += f"Row {i+1}: {dict(list(row.items())[:2])}\n"

                elif tool_name == "explain":
                    res = tool_explain(tool_args["sql"])
                    text = f"Query analysis: {'✅ Safe' if res['ok'] else '❌ Issues found'}\n"
                    if res.get("issues"):
                        text += "".join(f"• {i['message']} ({i['severity']})\n" for i in res["issues"])
                    if res.get("suggestions"):
                        text += "".join(f"• {s}\n" for s in res["suggestions"])

                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                    }

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}]},
                }

            # ---- Unbekannte Methode ----
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        except Exception as e:
            logging.exception("request_failed")
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": str(e)},
            }


def run_mcp_server():
    logging.info("mssql_mcp_server starting (MCP compliant)")
    server = MCPServer()

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            logging.error("invalid_json")
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        # ==== Notifications (ohne id) NICHT beantworten ====
        if req.get("id") is None:
            try:
                method = req.get("method")
                # akzeptiere gängige Notifications laut einigen Clients
                if method in ("ping", "notifications/ping", "$/cancelRequest"):
                    logging.debug("notification received: %s", method)
                else:
                    logging.debug("notification ignored: %s", method)
            except Exception:
                logging.exception("notification handling failed")
            # KEINE Antwort schreiben!
            continue

        # ==== Normale Requests ====
        resp = server.handle_request(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
