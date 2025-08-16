"""
title: MSSQL MCP (HTTP)
author: You
version: 1.0.4
license: MIT
description: Call MSSQL MCP over HTTP (tables, columns, query, paginate, explain, columns_with_examples, stats, value_counts, discover)
requirements: requests
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import requests
import re


class Tools:
    # ---------------- Valves (global & user) ----------------
    class Valves(BaseModel):
        mcp_url: str = Field(
            default="http://192.168.0.163:8000/mcp",
            description="MCP endpoint URL",
        )
        basic_auth_user: str = Field(
            default="", description="Basic auth user (optional)"
        )
        basic_auth_pass: str = Field(
            default="", description="Basic auth password (optional)"
        )
        timeout_s: int = Field(default=60, description="HTTP timeout (seconds)")
        default_fetch: int = Field(
            default=100, description="Default FETCH size for paginate"
        )
        server_row_limit_hint: int = Field(default=500, description="Informative only")

    class UserValves(BaseModel):
        allow_tables: str = Field(
            default="",
            description="Comma separated allowlist of tables (exact names incl. brackets if needed)",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ---------------- intern ----------------
    def _auth(self):
        if self.valves.basic_auth_user:
            return (self.valves.basic_auth_user, self.valves.basic_auth_pass or "")
        return None

    def _call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(
            self.valves.mcp_url,
            json=payload,
            timeout=self.valves.timeout_s,
            auth=self._auth(),
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid response from MCP (not a dict)"}
        if not data.get("ok", False):
            return {"ok": False, "error": data.get("error", "unknown error")}
        return data["result"]

    def _get_user_valves(self, __user__: Any) -> Dict[str, Any]:
        if not __user__:
            return {}
        if isinstance(__user__, dict):
            uv = __user__.get("valves", {})
        else:
            uv = getattr(__user__, "valves", {})
        if hasattr(uv, "model_dump"):
            try:
                return uv.model_dump()
            except Exception:
                pass
        return uv if isinstance(uv, dict) else {}

    def _check_table(self, table: str, __user__: Any = None):
        uv = self._get_user_valves(__user__)
        allow = (uv.get("allow_tables") or "").strip()
        if allow:
            allowed = {t.strip() for t in allow.split(",") if t.strip()}
            if table not in allowed:
                raise PermissionError(f"Table '{table}' not allowed for this user")

    # ---------------- Grund-APIs (1:1 MCP) ----------------
    def selftest(self) -> Dict[str, Any]:
        return {"ok": True, "msg": "tool returns plain dict"}

    def ping(self, __user__: Any = None) -> Dict[str, Any]:
        return self._call({"action": "ping"})

    def tables(self, __user__: Any = None) -> List[str]:
        res = self._call({"action": "tables"})
        if isinstance(res, dict) and "tables" in res:
            return res["tables"]
        return res

    def columns(self, table: str, __user__: Any = None) -> List[Dict[str, Any]]:
        self._check_table(table, __user__)
        return self._call({"action": "columns", "table": table})

    def query(self, sql: str, __user__: Any = None) -> Dict[str, Any]:
        return self._call({"action": "query", "sql": sql})

    def paginate(
        self,
        sql: str,
        offset: int = 0,
        fetch: Optional[int] = None,
        __user__: Any = None,
    ) -> Dict[str, Any]:
        f = int(fetch or self.valves.default_fetch)
        return self._call(
            {"action": "paginate", "sql": sql, "offset": int(offset), "fetch": f}
        )

    def explain(self, sql: str, __user__: Any = None) -> Dict[str, Any]:
        return self._call({"action": "explain", "sql": sql})

    def columns_with_examples(
        self, table: str, n: int = 3, __user__: Any = None
    ) -> Dict[str, Any]:
        self._check_table(table, __user__)
        return self._call(
            {"action": "columns_with_examples", "table": table, "n": int(n)}
        )

    def stats(
        self, table: str, sample_n: int = 5, __user__: Any = None
    ) -> Dict[str, Any]:
        self._check_table(table, __user__)
        return self._call(
            {"action": "stats", "table": table, "sample_n": int(sample_n)}
        )

    # ---------------- Zusatz-APIs ----------------

    def value_counts(
        self,
        table: str,
        column: str,
        top_k: int = 20,
        include_null_bucket: bool = True,
        __user__: Any = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        """
        Häufigste Werte (z. B. Codes/Länder) – **ohne ORDER BY im inneren Select**.
        Wir sortieren im äußeren Select (damit MCP.paginate OFFSET/FETCH anhängen kann),
        und vermeiden so den SQL-Fehler in derived tables.
        """
        self._check_table(table, __user__)
        tbl = f"[{table}]" if not re.search(r"[\[\]]", table) else table
        col = f"[{column}]" if not re.search(r"[\[\]]", column) else column

        if include_null_bucket:
            inner = (
                f"SELECT ISNULL(CAST(NULLIF(LTRIM(RTRIM({col})), '') AS NVARCHAR(100)), N'∅') AS value, "
                f"       COUNT(*) AS cnt "
                f"FROM {tbl} "
                f"GROUP BY ISNULL(CAST(NULLIF(LTRIM(RTRIM({col})), '') AS NVARCHAR(100)), N'∅')"
            )
        else:
            inner = (
                f"SELECT CAST({col} AS NVARCHAR(100)) AS value, COUNT(*) AS cnt "
                f"FROM {tbl} "
                f"WHERE {col} IS NOT NULL AND LTRIM(RTRIM({col})) <> '' "
                f"GROUP BY CAST({col} AS NVARCHAR(100))"
            )

        # WICHTIG: kein ORDER BY im inneren Select!
        wrapped_ordered = f"SELECT * FROM (\n{inner}\n) AS _vc ORDER BY cnt DESC"

        # Jetzt paginieren (MCP hängt OFFSET/FETCH an das äußere ORDER BY an)
        res = self.paginate(
            sql=wrapped_ordered, offset=0, fetch=int(top_k), __user__=__user__
        )

        out = {
            "table": table,
            "column": column,
            "top_k": int(top_k),
            "columns": res.get("columns", ["value", "cnt"]),
            "rows": res.get("rows", []),
            "row_count": res.get("row_count", 0),
            "truncated": bool(res.get("truncated", False)),
        }
        if debug:
            out["debug"] = {"wrapped_sql": wrapped_ordered}
        return out

    def _maybe_sample(
        self, table: str, wanted_cols: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        try:
            tbl = f"[{table}]" if not re.search(r"[\[\]]", table) else table
            if wanted_cols:
                cols = ", ".join(
                    f"[{c}]" if not re.search(r"[\[\]]", c) else c for c in wanted_cols
                )
            else:
                cols = "*"
            sql = f"SELECT {cols} FROM {tbl} ORDER BY 1"
            res = self.paginate(sql=sql, offset=0, fetch=2)
            return res.get("rows", [])[:2]
        except Exception:
            return []

    def discover(
        self,
        question: str,
        max_tables: int = 2,
        examples_per_col: int = 1,
        slim: bool = True,
        __user__: Any = None,
    ) -> Dict[str, Any]:
        all_tables = self.tables()

        def _score(t: str) -> int:
            q = question.lower()
            s = t.lower()
            score = 0
            for tok in {w for w in re.split(r"[\s\$_\-]+", q) if len(w) >= 3}:
                if tok in s:
                    score += 2
            return score

        ranked = sorted(
            ((t, _score(t)) for t in all_tables), key=lambda x: x[1], reverse=True
        )
        picked = [t for t, sc in ranked if sc > 0][:max_tables] or [
            t for t, _ in ranked[:max_tables]
        ]

        details = []
        for t in picked:
            try:
                if slim:
                    cols = self.columns(t)
                    cols = cols[:5]  # nur erste 5 Spalten
                    rows = self._maybe_sample(
                        t, wanted_cols=[c.get("column") for c in cols[:2]]
                    )
                    details.append(
                        {
                            "table": t,
                            "columns": [c.get("column") for c in cols],
                            "sample_rows": rows,
                        }
                    )
                else:
                    cwe = self.columns_with_examples(
                        table=t, n=int(examples_per_col), __user__=__user__
                    )
                    details.append({"table": t, "columns_with_examples": cwe})
            except Exception as ex:
                details.append({"table": t, "error": str(ex)})

        return {
            "ok": True,
            "question": question,
            "candidates": picked,
            "details": details,
        }
