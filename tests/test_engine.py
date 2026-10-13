import unittest
import sqlite3
from server.engine import SafeSQLiteEngine, MCPSentryServer, QuerySecurityError


class TestSafeSQLiteEngine(unittest.TestCase):
    def setUp(self):
        # Create an in-memory DB and seed sample data
        self.engine = SafeSQLiteEngine(":memory:")
        conn = self.engine.connect()
        conn.execute("PRAGMA query_only = OFF;")  # briefly allow seed
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);")
        conn.execute("INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com'), ('Bob', 'bob@example.com');")
        conn.commit()
        conn.execute("PRAGMA query_only = ON;")

    def test_safe_select_execution(self):
        result = self.engine.execute_query("SELECT id, name FROM users ORDER BY id;")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["rows"][0]["name"], "Alice")
        self.assertEqual(result["rows"][1]["name"], "Bob")

    def test_mutation_block_insert(self):
        with self.assertRaises(QuerySecurityError):
            self.engine.execute_query("INSERT INTO users (name, email) VALUES ('Eve', 'eve@evil.com');")

    def test_mutation_block_drop(self):
        with self.assertRaises(QuerySecurityError):
            self.engine.execute_query("DROP TABLE users;")

    def test_semicolon_stacking_blocked(self):
        with self.assertRaises(QuerySecurityError):
            self.engine.execute_query("SELECT 1; DROP TABLE users;")

    def test_mcp_tools_list(self):
        server = MCPSentryServer(":memory:")
        resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("safe_sql_query", tool_names)
        self.assertIn("get_database_schema", tool_names)


if __name__ == "__main__":
    unittest.main()
