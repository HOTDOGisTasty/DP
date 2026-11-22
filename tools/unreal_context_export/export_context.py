"""Read-only Unreal Python exporter for allowlisted DP assets."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback

import unreal

SCHEMA = "dp.unreal.context/v1"


def safe_property(obj, name):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return None


def object_path(value):
    if value is None:
        return None
    try:
        return value.get_path_name()
    except Exception:
        return str(value)


def scalar(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [scalar(item) for item in value]
    return object_path(value)


def asset_filename(path):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.strip("/")) + ".json"


def package_file_metadata(package_name):
    result = {"packageName": package_name, "file": None, "sha256": None}
    try:
        filename = unreal.PackageTools.find_package_file_without_extension(package_name)
        if filename:
            source = Path(str(filename))
            result["file"] = str(source)
            if source.is_file():
                result["sizeBytes"] = source.stat().st_size
                digest = hashlib.sha256()
                with source.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                result["sha256"] = digest.hexdigest()
    except Exception as exc:
        result["metadataError"] = str(exc)
    return result


def material_graph(asset):
    nodes = []
    try:
        expressions = list(unreal.MaterialEditingLibrary.get_material_expressions(asset))
        input_reader = unreal.MaterialEditingLibrary.get_inputs_for_material_expression
    except Exception:
        expressions = list(unreal.MaterialEditingLibrary.get_material_function_expressions(asset))
        input_reader = unreal.MaterialEditingLibrary.get_inputs_for_material_function_expression
    for expression in expressions:
        input_names = list(
            unreal.MaterialEditingLibrary.get_material_expression_input_names(expression)
        )
        input_types = list(
            unreal.MaterialEditingLibrary.get_material_expression_input_types(expression)
        )
        inputs = list(input_reader(asset, expression))
        pins = []
        links = []
        for index, name in enumerate(input_names):
            source = inputs[index] if index < len(inputs) else None
            pin = {
                "name": str(name),
                "direction": "input",
                "type": input_types[index] if index < len(input_types) else None,
                "connected": source is not None,
            }
            if source is not None:
                output_name = ""
                try:
                    result = unreal.MaterialEditingLibrary.get_input_node_output_name_for_material_expression(
                        expression, source
                    )
                    if isinstance(result, tuple):
                        output_name = str(result[-1])
                    elif result is not None:
                        output_name = str(result)
                except Exception:
                    pass
                link = {
                    "fromNode": object_path(source),
                    "fromOutput": output_name,
                    "toInput": str(name),
                }
                pin["link"] = link
                links.append(link)
            pins.append(pin)
        outputs = [
            {"name": str(name), "direction": "output"}
            for name in unreal.MaterialEditingLibrary.get_material_expression_output_names(expression)
        ]
        node = {
            "id": object_path(expression),
            "class": expression.get_class().get_name(),
            "title": str(safe_property(expression, "parameter_name") or expression.get_name()),
            "position": {
                "x": scalar(safe_property(expression, "material_expression_editor_x")),
                "y": scalar(safe_property(expression, "material_expression_editor_y")),
            },
            "description": scalar(safe_property(expression, "desc")),
            "group": scalar(safe_property(expression, "group")),
            "pins": pins + outputs,
            "inputLinks": links,
        }
        function = safe_property(expression, "material_function")
        if function:
            node["materialFunction"] = object_path(function)
        nodes.append(node)
    return {
        "kind": "Material",
        "coverage": {"nodes": True, "positions": True, "pins": True, "links": True,
                     "comments": False},
        "nodes": sorted(nodes, key=lambda item: item["id"] or ""),
    }


def export_asset(path):
    document = {
        "schemaVersion": SCHEMA,
        "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
        "engineVersion": unreal.SystemLibrary.get_engine_version(),
        "readOnly": True,
        "asset": {"objectPath": path},
        "dependencies": [],
        "referencers": [],
        "graph": {"kind": "Unknown", "coverage": {}, "nodes": []},
        "validation": {"status": "not_run", "issues": []},
        "errors": [],
    }
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            raise RuntimeError("Asset does not exist")
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if asset is None:
            raise RuntimeError("load_asset returned None")
        package_name = str(asset.get_outermost().get_name())
        document["asset"].update({
            "class": asset.get_class().get_name(),
            **package_file_metadata(package_name),
        })
        document["dependencies"] = sorted(map(str,
            unreal.EditorAssetLibrary.list_asset_dependencies(path, False)))
        document["referencers"] = sorted(map(str,
            unreal.EditorAssetLibrary.find_package_referencers_for_asset(path, False)))
        try:
            document["graph"] = material_graph(asset)
        except Exception as exc:
            document["graph"]["coverage"]["nodes"] = False
            document["errors"].append({"stage": "graph", "message": str(exc)})
        try:
            validator = unreal.get_editor_subsystem(unreal.EditorValidatorSubsystem)
            verdict = validator.is_object_valid(asset, unreal.DataValidationUsecase.SCRIPT)
            document["validation"]["status"] = str(verdict)
        except Exception as exc:
            document["validation"]["issues"].append({"message": str(exc)})
    except Exception as exc:
        document["errors"].append({
            "stage": "asset", "message": str(exc), "traceback": traceback.format_exc()
        })
    return document


def main(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    output_root = Path(config["outputRoot"])
    graph_root = output_root / "graphs"
    graph_root.mkdir(parents=True, exist_ok=True)
    index = {"schemaVersion": SCHEMA, "assets": []}
    for path in sorted(set(config.get("assets", []))):
        document = export_asset(path)
        filename = asset_filename(path)
        (graph_root / filename).write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index["assets"].append({
            "objectPath": path,
            "file": "graphs/" + filename,
            "class": document["asset"].get("class"),
            "sha256": document["asset"].get("sha256"),
            "errors": len(document["errors"]),
        })
    (output_root / "assets-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unreal.log("DP_CONTEXT_EXPORT=" + str(output_root / "assets-index.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: export_context.py <config.json>")
    main(sys.argv[1])
