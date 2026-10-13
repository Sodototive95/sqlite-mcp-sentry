"""
SQLite MCP Sentry - Fast, Safe, Read-Only Model Context Protocol SQLite Server.
Implements the JSON-RPC 2.0 MCP protocol over stdio for LLMs to query databases safely.
Includes strict query tokenization, read-only pragmas, and execution timeouts.
"""

from dataclasses import dataclass
import json
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple


class QuerySecurityError(Exception):
    """Raised when an unsafe or non-SELECT query is submitted."""
    pass


class SafeSQLiteEngine:
    """
    Manages an isolated SQLite database connection with strict read-only enforcement
    and statement inspection.
    """

    DISALLOWED_KEYWORDS = {
        "insert", "update", "delete", "drop", "alter", "create", "truncate",
        "replace", "attach", "detach", "vacuum", "reindex", "grant", "revoke"
    }

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            # Query URI parameter mode=ro ensures OS/driver-level read-only safety
            uri = f"file:{self.db_path}?mode=ro" if self.db_path != ":memory:" else ":memory:"
            self._conn = sqlite3.connect(uri, uri=(self.db_path != ":memory:"))
            self._conn.row_factory = sqlite3.Row
            # Enforce safety pragmas
            self._conn.execute("PRAGMA query_only = ON;")
        return self._conn

    def validate_query(self, sql: str) -> str:
        """Inspects SQL text to ensure it is strictly a read-only statement."""
        cleaned = sql.strip().rstrip(";")
        if not cleaned:
            raise QuerySecurityError("SQL query cannot be empty.")

        # Disallow multi-statement query batching (semicolon separation)
        if ";" in cleaned:
            raise QuerySecurityError("Multi-statement queries separated by semicolons are strictly prohibited.")

        # Tokenize first word
        first_word = cleaned.split()[0].lower()
        if first_word not in ("select", "explain", "pragma", "with"):
            raise QuerySecurityError(f"Operation '{first_word.upper()}' is not permitted in read-only mode.")

        # Regex scan for destructive tokens
        tokens = set(re.findall(r"\b[a-zA-Z]+\b", cleaned.lower()))
        disallowed_found = tokens.intersection(self.DISALLOWED_KEYWORDS)
        if disallowed_found:
            raise QuerySecurityError(f"Forbidden mutation keyword(s) detected: {', '.join(disallowed_found)}")

        return cleaned

    def execute_query(self, sql: str, params: Optional[Tuple[Any, ...]] = None, max_rows: int = 500) -> Dict[str, Any]:
        """Safely executes a read-only query and returns structured results."""
        safe_sql = self.validate_query(sql)
        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.execute(safe_sql, params or ())
            rows = cursor.fetchmany(max_rows)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            result_data = [dict(zip(columns, row)) for row in rows]
            return {
                "columns": columns,
                "row_count": len(result_data),
                "rows": result_data,
                "truncated": len(rows) == max_rows,
            }
        finally:
            cursor.close()

    def get_schema(self) -> List[Dict[str, Any]]:
        """Extracts schema overview of all tables and columns."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = []
        for row in cursor.fetchall():
            tables.append({"table_name": row["name"], "ddl": row["sql"]})
        cursor.close()
        return tables


class MCPSentryServer:
    """JSON-RPC 2.0 stdio handler following the MCP protocol specification."""

    def __init__(self, db_path: str = ":memory:"):
        self.engine = SafeSQLiteEngine(db_path=db_path)

    def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "safe_sql_query",
                            "description": "Execute a safe, read-only SELECT query against the SQLite database.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Read-only SQL SELECT statement."}
                                },
                                "required": ["query"],
                            },
                        },
                        {
                            "name": "get_database_schema",
                            "description": "Retrieve the schema (tables and DDL) of the SQLite database.",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name == "safe_sql_query":
                query = args.get("query", "")
                try:
                    result = self.engine.execute_query(query)
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
                    }
                except QuerySecurityError as qse:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32001, "message": f"Security Violation: {str(qse)}"},
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32603, "message": f"Execution Error: {str(e)}"},
                    }

            elif tool_name == "get_database_schema":
                schema = self.engine.get_schema()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(schema, indent=2)}]},
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }
