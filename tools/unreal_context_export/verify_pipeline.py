"""One-command verification for the DP context/export foundation."""

from datetime import datetime, timezone
import argparse
import compileall
import io
import json
from pathlib import Path
import unittest

from acceptance_gate import evaluate
from run_checks import run as run_export_checks
from validate_action_log import validate as validate_log


def verify(workspace, context_root, evidence_path):
    workspace, context_root = Path(workspace), Path(context_root)
    tool_root = Path(__file__).resolve().parent
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(tool_root / "tests"))
    test_result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
    compile_ok = compileall.compile_dir(str(tool_root), quiet=1)
    export_report = run_export_checks(context_root)
    action_issues = []
    action_root = context_root / "actions"
    for path in sorted(action_root.glob("*.jsonl")) if action_root.is_dir() else []:
        action_issues.extend(f"{path.name}: {item}" for item in validate_log(path))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    acceptance = evaluate(evidence)
    hard_failures = (
        (0 if test_result.wasSuccessful() else 1)
        + (0 if compile_ok else 1)
        + (1 if export_report["status"] == "fail" else 0)
        + len(action_issues)
    )
    status = "fail" if hard_failures else (
        "partial" if acceptance["status"] == "partial" or export_report["status"] == "partial"
        else "pass"
    )
    return {
        "schemaVersion": "dp.unreal.pipeline-verification/v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "hardFailures": hard_failures,
        "python": {
            "testsRun": test_result.testsRun,
            "failures": len(test_result.failures),
            "errors": len(test_result.errors),
            "compileAll": compile_ok,
            "output": output.getvalue(),
        },
        "exports": export_report,
        "actionLogIssues": action_issues,
        "acceptance": acceptance,
        "workspace": str(workspace),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--context", default=None)
    parser.add_argument("--evidence", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    workspace = Path(args.workspace)
    context = Path(args.context) if args.context else workspace / "context/unreal"
    evidence = Path(args.evidence) if args.evidence else Path(__file__).resolve().parent / "pilot-evidence.json"
    output = Path(args.output) if args.output else context / "validation/pipeline.json"
    report = verify(workspace, context, evidence)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "hardFailures": report["hardFailures"],
        "testsRun": report["python"]["testsRun"],
        "assets": report["exports"]["summary"]["assets"],
    }, sort_keys=True))
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
