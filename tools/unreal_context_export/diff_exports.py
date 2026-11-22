"""Semantic diff for two DP Unreal context export roots."""

import json
from pathlib import Path
import sys


def load_assets(root):
    root = Path(root)
    index = json.loads((root / "assets-index.json").read_text(encoding="utf-8"))
    return {
        item["objectPath"]: json.loads((root / item["file"]).read_text(encoding="utf-8"))
        for item in index.get("assets", [])
    }


def links(document):
    return {
        (link.get("fromNode"), node.get("id"), link.get("fromOutput"), link.get("toInput"))
        for node in document.get("graph", {}).get("nodes", [])
        for link in node.get("inputLinks", [])
    }


def stable_node(node):
    ignored = {"exportedAtUtc"}
    return {key: value for key, value in node.items() if key not in ignored}


def compare_asset(before, after):
    before_nodes = {item.get("id"): item for item in before.get("graph", {}).get("nodes", [])}
    after_nodes = {item.get("id"): item for item in after.get("graph", {}).get("nodes", [])}
    common = before_nodes.keys() & after_nodes.keys()
    changed = sorted(node_id for node_id in common
                     if stable_node(before_nodes[node_id]) != stable_node(after_nodes[node_id]))
    before_links, after_links = links(before), links(after)
    before_deps, after_deps = set(before.get("dependencies", [])), set(after.get("dependencies", []))
    return {
        "addedNodes": sorted(after_nodes.keys() - before_nodes.keys()),
        "removedNodes": sorted(before_nodes.keys() - after_nodes.keys()),
        "changedNodes": changed,
        "addedLinks": [list(item) for item in sorted(after_links - before_links)],
        "removedLinks": [list(item) for item in sorted(before_links - after_links)],
        "addedDependencies": sorted(after_deps - before_deps),
        "removedDependencies": sorted(before_deps - after_deps),
    }


def diff(before_root, after_root):
    before, after = load_assets(before_root), load_assets(after_root)
    common = before.keys() & after.keys()
    changed = {}
    for path in sorted(common):
        details = compare_asset(before[path], after[path])
        if any(details.values()):
            changed[path] = details
    return {
        "schemaVersion": "dp.unreal.diff/v1",
        "addedAssets": sorted(after.keys() - before.keys()),
        "removedAssets": sorted(before.keys() - after.keys()),
        "changedAssets": changed,
    }


def main(argv):
    if len(argv) < 3:
        raise SystemExit("Usage: diff_exports.py <before-root> <after-root> [output.json]")
    result = diff(argv[1], argv[2])
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(argv) > 3:
        Path(argv[3]).write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main(sys.argv)
