"""Conservative, report-only graph readability checks."""

from collections import Counter
import math


DEFAULTS = {"longLinkDistance": 1400.0, "highFanout": 4}


def audit_graph(document, rules=None):
    rules = {**DEFAULTS, **(rules or {})}
    graph = document.get("graph", {})
    coverage = graph.get("coverage", {})
    issues = []
    if not coverage.get("nodes"):
        return [{"code": "coverage.nodes", "severity": "info",
                 "message": "Node coverage is incomplete; layout was not judged."}]
    nodes = graph.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes if node.get("id")}
    fanout = Counter()
    seen_links = set()
    for target in nodes:
        target_pos = target.get("position", {})
        for link in target.get("inputLinks", []):
            key = (link.get("fromNode"), target.get("id"), link.get("toInput"))
            if key in seen_links:
                continue
            seen_links.add(key)
            source = by_id.get(link.get("fromNode"))
            if not source:
                issues.append({"code": "link.missing_source", "severity": "warning",
                               "node": target.get("id"), "message": "Link source is absent from export."})
                continue
            fanout[source.get("id")] += 1
            source_pos = source.get("position", {})
            values = (source_pos.get("x"), source_pos.get("y"),
                      target_pos.get("x"), target_pos.get("y"))
            if all(isinstance(value, (int, float)) for value in values):
                distance = math.hypot(values[2] - values[0], values[3] - values[1])
                if distance > rules["longLinkDistance"]:
                    issues.append({
                        "code": "link.long", "severity": "warning",
                        "fromNode": source.get("id"), "toNode": target.get("id"),
                        "distance": round(distance, 1),
                        "message": "Long graph connection; inspect grouping or a named reroute.",
                    })
    for node_id, count in sorted(fanout.items()):
        if count >= rules["highFanout"]:
            issues.append({
                "code": "node.high_fanout", "severity": "info", "node": node_id,
                "fanout": count,
                "message": "Frequently reused value; inspect whether a named reroute improves readability.",
            })
    if coverage.get("comments") is False:
        issues.append({"code": "coverage.comments", "severity": "info",
                       "message": "Comment coverage is unavailable; comment organization was not judged."})
    return issues
