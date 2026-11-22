import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_export import SCHEMA, validate
from layout_audit import audit_graph


class ExportValidationTests(unittest.TestCase):
    def test_valid_minimal_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "graphs").mkdir()
            document = {
                "schemaVersion": SCHEMA,
                "asset": {"objectPath": "/Game/DP/Test"},
                "graph": {"coverage": {"nodes": False}},
            }
            (root / "graphs/Test.json").write_text(json.dumps(document), encoding="utf-8")
            index = {
                "schemaVersion": SCHEMA,
                "assets": [{"objectPath": "/Game/DP/Test", "file": "graphs/Test.json"}],
            }
            (root / "assets-index.json").write_text(json.dumps(index), encoding="utf-8")
            self.assertEqual([], validate(root))

    def test_missing_document_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            index = {
                "schemaVersion": SCHEMA,
                "assets": [{"objectPath": "/Game/DP/Missing", "file": "graphs/missing.json"}],
            }
            (root / "assets-index.json").write_text(json.dumps(index), encoding="utf-8")
            self.assertTrue(any("missing document" in issue for issue in validate(root)))

    def test_layout_audit_reports_long_link_and_fanout(self):
        source = {"id": "Source", "position": {"x": 0, "y": 0}, "inputLinks": []}
        targets = [
            {"id": f"Target{index}", "position": {"x": 2000, "y": index * 10},
             "inputLinks": [{"fromNode": "Source", "toInput": "Value"}]}
            for index in range(4)
        ]
        document = {"graph": {"coverage": {"nodes": True, "comments": False},
                              "nodes": [source, *targets]}}
        codes = [item["code"] for item in audit_graph(document)]
        self.assertEqual(4, codes.count("link.long"))
        self.assertIn("node.high_fanout", codes)


if __name__ == "__main__":
    unittest.main()
