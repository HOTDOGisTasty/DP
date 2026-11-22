"""Append-only JSONL action records for DP automation."""

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


def append_action(log_path, *, operation, status, assets=(), verification=None,
                  actor="codex", details=None):
    record = {
        "schemaVersion": "dp.unreal.action/v1",
        "id": str(uuid.uuid4()),
        "timestampUtc": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "operation": operation,
        "status": status,
        "assets": sorted(set(assets)),
        "verification": verification or {},
        "details": details or {},
    }
    target = Path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record
