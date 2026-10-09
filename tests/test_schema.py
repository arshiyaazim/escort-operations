import ast
import json
import sqlite3
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SqliteSchemaTests(unittest.TestCase):
    def test_schema_and_synthetic_seed_are_executable(self):
        source = Path(__file__).resolve().parents[1] / "backend" / "main.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        schema = next(node.value.value for node in module.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets))
        seed_fn = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "seed")
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(schema)
        namespace = {"datetime": datetime, "timezone": timezone, "uuid": uuid, "json": json}
        exec(compile(ast.Module(body=[seed_fn], type_ignores=[]), str(source), "exec"), namespace)
        namespace["seed"](conn)
        programs = conn.execute("SELECT mother_vessel,lighter_vessel FROM programs").fetchall()
        self.assertEqual(len(programs), 2)
        self.assertEqual({row["mother_vessel"] for row in programs}, {"MV DEMO STAR"})
        self.assertEqual({row["lighter_vessel"] for row in programs}, {"DEMO LIGHTER A", "DEMO LIGHTER B"})


if __name__ == "__main__":
    unittest.main()
