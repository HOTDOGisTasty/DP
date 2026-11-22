import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest_mcp_blueprint import normalize, parse_dsl


class BlueprintMcpIngestTests(unittest.TestCase):
    def test_parses_nested_graph_dsl(self):
        ast = parse_dsl('(fn Test (Value) (return (and Value "hello world")))')
        self.assertEqual("fn", ast[0][0])
        self.assertEqual("hello world", ast[0][3][1][2])

    def test_preserves_empty_and_nonempty_graphs(self):
        raw = {"returnValue": {"graphs": [
            {"path": "/Game/BP:EventGraph", "name": "EventGraph", "dsl": ""},
            {"path": "/Game/BP:Check", "name": "Check", "dsl": "(fn Check () (return true))"},
        ]}}
        result = normalize(raw, "/Game/BP")
        self.assertEqual([], result["graph"]["subgraphs"][0]["ast"])
        self.assertEqual("fn", result["graph"]["subgraphs"][1]["ast"][0][0])
        self.assertFalse(result["graph"]["coverage"]["nodes"])


if __name__ == "__main__":
    unittest.main()
