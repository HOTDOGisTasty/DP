"""Normalize the official UE 5.8 PCG MCP GetGraphStructure response."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re

from validate_export import SCHEMA


POSITION = re.compile(r"^\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)$")


def parse_position(value):
    match = POSITION.match(str(value or ""))
    if not match:
        return {"x": None, "y": None}
    return {"x": float(match.group(1)), "y": float(match.group(2))}


def normalize(raw, asset_path, dependencies=(), referencers=()):
    structure = raw.get("returnValue", raw)
    nodes_by_name = {}
    nodes = []
    for source in structure.get("nodes", []):
        node = {
            "id": source.get("path") or source.get("name"),
            "name": source.get("name"),
            "title": source.get("title"),
            "class": source.get("nodeType"),
            "position": parse_position(source.get("position")),
            "description": source.get("comment") or "",
            "enabled": source.get("bEnabled"),
            "properties": source.get("paramOverrides", {}),
            "pins": [],
            "inputLinks": [],
        }
        nodes.append(node)
        nodes_by_name[source.get("name")] = node
    for edge in structure.get("edges", []):
        source = nodes_by_name.get(edge.get("srcNode"))
        target = nodes_by_name.get(edge.get("destNode"))
        if target is None:
            continue
        link = {
            "fromNode": source.get("id") if source else edge.get("srcNode"),
            "fromOutput": edge.get("srcPin"),
            "toInput": edge.get("destPin"),
        }
        target["inputLinks"].append(link)
        target["pins"].append({
            "name": edge.get("destPin"), "direction": "input",
            "connected": True, "link": link,
        })
    return {
        "schemaVersion": SCHEMA,
        "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
        "engineVersion": "5.8 (official PCG MCP)",
        "readOnly": True,
        "asset": {"objectPath": asset_path, "class": "PCGGraph"},
        "dependencies": sorted(set(dependencies)),
        "referencers": sorted(set(referencers)),
        "graph": {
            "kind": "PCG",
            "name": structure.get("name"),
            "description": structure.get("description"),
            "coverage": {"nodes": True, "positions": True, "pins": "connected_only",
                         "links": True, "comments": True, "parameters": True},
            "nodes": nodes,
        },
        "validation": {"status": "not_run", "required": False,
                       "reason": "Read-only export; no asset mutation", "issues": []},
        "errors": [],
    }


def write_export(document, root):
    root = Path(root)
    graph_root = root / "graphs"
    graph_root.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", document["asset"]["objectPath"].strip("/")) + ".json"
    relative = "graphs/" + name
    (root / relative).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index_path = root / "assets-index.json"
    index = {"schemaVersion": SCHEMA, "assets": []}
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = {"objectPath": document["asset"]["objectPath"], "file": relative,
             "class": document["asset"].get("class"), "errors": len(document["errors"])}
    index["assets"] = [item for item in index.get("assets", [])
                       if item.get("objectPath") != entry["objectPath"]]
    index["assets"].append(entry)
    index["assets"].sort(key=lambda item: item["objectPath"])
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    return root / relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw")
    parser.add_argument("asset_path")
    parser.add_argument("output_root")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    print(write_export(normalize(
        raw, args.asset_path,
        dependencies=raw.get("dependencies", ()),
        referencers=raw.get("referencers", ()),
    ), args.output_root))


if __name__ == "__main__":
    main()
