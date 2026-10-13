# SQLite MCP Sentry

[![CI](https://github.com/Sodototive95/sqlite-mcp-sentry/actions/workflows/ci.yml/badge.svg)](https://github.com/Sodototive95/sqlite-mcp-sentry/actions)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

A secure, hardened **Model Context Protocol (MCP)** server providing read-only SQL access for LLMs (Claude, Gemini, OpenAI) to query SQLite databases without the risk of data mutation or SQL injection.

## Why SQLite MCP Sentry?
Giving Large Language Models write access or unrestricted raw SQL execution can lead to accidental table drops, unauthorized mutations, or multi-statement injections.

SQLite MCP Sentry enforces **multi-tier defense in depth**:
1. **URI Mode Read-Only (`mode=ro`):** SQLite driver-level write locks.
2. **SQLite Pragmas:** Enforces `PRAGMA query_only = ON`.
3. **AST / Token Scanning:** Rejects query batching (semicolon separation) and mutation keywords (`DROP`, `ALTER`, `DELETE`, `UPDATE`, `INSERT`, `ATTACH`, `VACUUM`).
4. **Row Truncation Guards:** Caps query outputs to prevent context window token blowups.

## Protocol Support
Implements **Model Context Protocol (JSON-RPC 2.0)**:
- `tools/list`: Exposes `safe_sql_query` and `get_database_schema`.
- `tools/call`: Executes validated queries and returns structured text payloads.

## Usage Example

```python
from server.engine import MCPSentryServer

server = MCPSentryServer(db_path="/path/to/analytics.db")

# JSON-RPC tool invocation from an LLM orchestrator
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "safe_sql_query",
        "arguments": {"query": "SELECT country, count(*) FROM sessions GROUP BY country;"}
    }
}

response = server.handle_request(request)
print(response)
```

## Running Tests

Zero external third-party dependencies:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## License
MIT License. Created by Joel Rand.
