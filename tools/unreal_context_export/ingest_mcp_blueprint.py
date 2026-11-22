"""Normalize official UE 5.8 Blueprint MCP read_graph_dsl responses."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re

from ingest_mcp_pcg import write_export
from validate_export import SCHEMA


TOKEN = re.compile(r'''\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))''')


def parse_dsl(source):
    tokens = []
    for match in TOKEN.finditer(source or ""):
        left, right, quoted, symbol = match.groups()
        tokens.append(left or right or json.loads(quoted) if quoted else left or right or symbol)
    stack = [[]]
    for token in tokens:
        if token == "(":
            child = []
            stack[-1].append(child)
            stack.append(child)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("Unmatched closing parenthesis")
            stack.pop()
        else:
            stack[-1].append(token)
    if len(stack) != 1:
        raise ValueError("Unclosed parenthesis")
    return stack[0]


def normalize(raw, asset_path):
    payload = raw.get("returnValue", raw)
    subgraphs = []
    errors = []
    for graph in payload.get("graphs", []):
        source = graph.get("dsl", "")
        entry = {"path": graph.get("path"), "name": graph.get("name"),
                 "dsl": source, "ast": []}
        try:
            entry["ast"] = parse_dsl(source)
        except Exception as exc:
            errors.append({"stage": "blueprint_dsl", "graph": graph.get("path"),
                           "message": str(exc)})
        subgraphs.append(entry)
    return {
        "schemaVersion": SCHEMA,
        "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
        "engineVersion": "5.8 (official Blueprint MCP)",
        "readOnly": True,
        "asset": {"objectPath": asset_path, "class": "Blueprint",
                  "parentClass": payload.get("parentClass")},
        "dependencies": sorted(set(raw.get("dependencies", ()))),
        "referencers": sorted(set(raw.get("referencers", ()))),
        "graph": {
            "kind": "Blueprint",
            "coverage": {"blueprintDsl": True, "structuredAst": True, "nodes": False,
                         "positions": False, "pins": "dsl", "links": "dsl",
                         "comments": "dsl"},
            "nodes": [],
            "subgraphs": subgraphs,
        },
        "validation": {"status": payload.get("validationStatus", "not_run"),
                       "required": False, "reason": "Read-only export; no asset mutation",
                       "issues": []},
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw")
    parser.add_argument("asset_path")
    parser.add_argument("output_root")
    args = parser.parse_args()
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    print(write_export(normalize(raw, args.asset_path), args.output_root))


if __name__ == "__main__":
    main()
