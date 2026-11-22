import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diff_exports import diff
from validate_export import SCHEMA


def write_root(root, document):
    root = Path(root)
    (root / "graphs").mkdir(parents=True)
    (root / "graphs/a.json").write_text(json.dumps(document), encoding="utf-8")
    (root / "assets-index.json").write_text(json.dumps({
        "schemaVersion": SCHEMA,
        "assets": [{"objectPath": "/Game/A", "file": "graphs/a.json"}],
    }), encoding="utf-8")


class ExportDiffTests(unittest.TestCase):
    def test_reports_semantic_node_and_link_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder) / "before", Path(folder) / "after"
            base = {
                "dependencies": [],
                "graph": {"nodes": [
                    {"id": "A", "position": {"x": 0, "y": 0}, "inputLinks": []},
                    {"id": "B", "position": {"x": 1, "y": 0}, "inputLinks": []},
                ]},
            }
            changed = json.loads(json.dumps(base))
            changed["graph"]["nodes"][1]["position"]["x"] = 2
            changed["graph"]["nodes"][1]["inputLinks"] = [
                {"fromNode": "A", "fromOutput": "Out", "toInput": "In"}
            ]
            write_root(before, base)
            write_root(after, changed)
            result = diff(before, after)["changedAssets"]["/Game/A"]
            self.assertEqual(["B"], result["changedNodes"])
            self.assertEqual(1, len(result["addedLinks"]))
