import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acceptance_gate import evaluate
from action_log import append_action
from validate_action_log import validate


class AcceptanceAndLogTests(unittest.TestCase):
    def test_missing_gate_is_partial(self):
        result = evaluate({"compile": {"status": "pass"}}, required=("compile", "visualCapture"))
        self.assertEqual("partial", result["status"])

    def test_failed_gate_fails(self):
        result = evaluate({"compile": {"status": "fail"}}, required=("compile",))
        self.assertEqual("fail", result["status"])

    def test_action_record_round_trip_validates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "actions.jsonl"
            append_action(path, operation="test", status="verified")
            self.assertEqual([], validate(path))
