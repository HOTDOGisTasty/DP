import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_checks import run
from validate_export import SCHEMA


class CheckRunnerTests(unittest.TestCase):
    def test_reports_asset_counts_and_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "graphs").mkdir()
            document = {
                "schemaVersion": SCHEMA, "readOnly": True,
                "asset": {"objectPath": "/Game/Test"},
                "dependencies": ["/Game/Dep"], "referencers": [],
                "graph": {"kind": "PCG", "coverage": {"nodes": True, "comments": True},
                          "nodes": []},
                "validation": {"status": "not_run", "issues": []}, "errors": [],
            }
            (root / "graphs/test.json").write_text(json.dumps(document), encoding="utf-8")
            (root / "assets-index.json").write_text(json.dumps({
                "schemaVersion": SCHEMA,
                "assets": [{"objectPath": "/Game/Test", "file": "graphs/test.json"}],
            }), encoding="utf-8")
            result = run(root)
            self.assertEqual("partial", result["status"])
            self.assertEqual(1, result["assets"][0]["counts"]["dependencies"])

    def test_pass_requires_engine_validation_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "graphs").mkdir()
            document = {
                "schemaVersion": SCHEMA, "readOnly": True,
                "asset": {"objectPath": "/Game/Test"},
                "dependencies": [], "referencers": [],
                "graph": {"kind": "PCG", "coverage": {"nodes": True, "comments": True},
                          "nodes": []},
                "validation": {"status": "Valid", "issues": []}, "errors": [],
            }
            (root / "graphs/test.json").write_text(json.dumps(document), encoding="utf-8")
            (root / "assets-index.json").write_text(json.dumps({
                "schemaVersion": SCHEMA,
                "assets": [{"objectPath": "/Game/Test", "file": "graphs/test.json"}],
            }), encoding="utf-8")
            self.assertEqual("pass", run(root)["status"])
