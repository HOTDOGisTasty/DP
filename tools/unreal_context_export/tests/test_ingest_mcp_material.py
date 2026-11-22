import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest_mcp_material import normalize


class MaterialMcpIngestTests(unittest.TestCase):
    def test_filters_unwired_none_and_keeps_real_link(self):
        raw = {"returnValue": {"nodes": [{
            "id": "/Game/M.M:MaterialExpressionAdd_0",
            "properties": {"materialExpressionEditorX": 10, "materialExpressionEditorY": 20},
            "inputNames": ["A", "B"], "outputNames": [""],
            "inputLinks": [
                {"fromNode": "/Game/M.M:Source", "fromOutput": "", "toInput": "A"},
                {"fromNode": "None", "fromOutput": "", "toInput": "B"},
            ],
        }]}}
        result = normalize(raw, "/Game/M")
        node = result["graph"]["nodes"][0]
        self.assertEqual(1, len(node["inputLinks"]))
        self.assertTrue(node["pins"][0]["connected"])
        self.assertFalse(node["pins"][1]["connected"])


if __name__ == "__main__":
    unittest.main()
