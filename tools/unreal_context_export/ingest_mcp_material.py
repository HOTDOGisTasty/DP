"""Normalize a read-only material batch collected through official MCP tools."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from ingest_mcp_pcg import write_export
from validate_export import SCHEMA


def normalize(raw, asset_path, asset_class="MaterialFunction"):
    payload = raw.get("returnValue", raw)
    nodes = []
    for source in payload.get("nodes", []):
        properties = source.get("properties", {})
        links = [link for link in source.get("inputLinks", [])
                 if link.get("fromNode") not in (None, "", "None")]
        pins = [
            {"name": name, "direction": "input",
             "connected": any(link.get("toInput") == name for link in links)}
            for name in source.get("inputNames", [])
        ] + [
            {"name": name, "direction": "output"}
            for name in source.get("outputNames", [])
        ]
        nodes.append({
            "id": source.get("id"),
            "class": str(source.get("id", "")).rsplit(":", 1)[-1].split("_")[0],
            "title": properties.get("parameterName") or str(source.get("id", "")).rsplit(":", 1)[-1],
            "position": {
                "x": properties.get("materialExpressionEditorX"),
                "y": properties.get("materialExpressionEditorY"),
            },
            "description": properties.get("desc", ""),
            "group": properties.get("group"),
            "properties": properties,
            "pins": pins,
            "inputLinks": links,
        })
    return {
        "schemaVersion": SCHEMA,
        "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
        "engineVersion": "5.8 (official Material/Object MCP)",
        "readOnly": True,
        "asset": {"objectPath": asset_path, "class": asset_class},
        "dependencies": sorted(set(raw.get("dependencies", ()))),
        "referencers": sorted(set(raw.get("referencers", ()))),
        "graph": {
            "kind": "Material",
            "coverage": {"nodes": True, "positions": True, "pins": True,
                         "links": True, "comments": False, "properties": "selected"},
            "nodes": nodes,
        },
        "validation": {"status": "not_run", "required": False,
                       "reason": "Read-only export; no asset mutation", "issues": []},
        "errors": [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw")
    parser.add_argument("asset_path")
    parser.add_argument("output_root")
    parser.add_argument("--class", dest="asset_class", default="MaterialFunction")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    print(write_export(normalize(raw, args.asset_path, args.asset_class), args.output_root))


if __name__ == "__main__":
    main()
