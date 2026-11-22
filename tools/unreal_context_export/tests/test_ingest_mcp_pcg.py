import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest_mcp_pcg import normalize


class PcgMcpIngestTests(unittest.TestCase):
    def test_normalizes_nodes_edges_and_positions(self):
        raw = {"returnValue": {
            "name": "Example",
            "nodes": [
                {"name": "A", "path": "/Game/A:A", "position": "(0, 10)",
                 "title": "A", "nodeType": "Input", "bEnabled": True,
                 "comment": "", "paramOverrides": {}},
                {"name": "B", "path": "/Game/A:B", "position": "(250, -20)",
                 "title": "B", "nodeType": "Output", "bEnabled": True,
                 "comment": "Done", "paramOverrides": {}},
            ],
            "edges": [{"srcNode": "A", "srcPin": "Out", "destNode": "B", "destPin": "In"}],
        }}
        result = normalize(raw, "/Game/A")
        self.assertEqual("PCG", result["graph"]["kind"])
        self.assertEqual({"x": 250.0, "y": -20.0}, result["graph"]["nodes"][1]["position"])
        self.assertEqual("/Game/A:A", result["graph"]["nodes"][1]["inputLinks"][0]["fromNode"])


if __name__ == "__main__":
    unittest.main()
