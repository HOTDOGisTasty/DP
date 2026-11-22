"""Read a validated, rigid assembly directly from a BuildingTheme data asset."""

from hashlib import sha256
from itertools import product
import json
from math import isfinite

import unreal


def coordinates(value):
    return [value.x, value.y, value.z]


def transformed_mesh_corners(mesh, transform):
    box = mesh.get_bounding_box()
    return [
        coordinates(transform.transform_location(unreal.Vector(*point)))
        for point in product(*zip(coordinates(box.min), coordinates(box.max)))
    ]


def load_assembly(theme, *, expected_theme_id=None, slot_overrides=None):
    """Return size_cm, ordered native slot references and a value-based fingerprint."""
    if theme is None:
        raise ValueError("Ein Building-Theme fehlt.")
    size = coordinates(theme.get_editor_property("FixedAssemblySizeCm"))
    if not all(isfinite(value) and value > 0 for value in size):
        raise ValueError("Die Hülle muss drei positive, endliche Maße in cm haben.")
    if not theme.get_editor_property("SyntyOnly"):
        raise ValueError("Das feste Mansion-Kit erfordert SyntyOnly.")
    rows = list(theme.get_editor_property("FixedAssemblySlots"))
    if not rows:
        raise ValueError("Die feste Assembly enthält keine Slots.")
    catalog = list(theme.get_editor_property("Modules"))
    overrides = dict(slot_overrides or {})
    known_slots = {str(row.get_editor_property("SlotId")).strip() for row in rows}
    if unknown := overrides.keys() - known_slots:
        raise ValueError(f"Nicht zuordenbare Modul-Overrides: {', '.join(sorted(unknown))}.")
    by_path = {path: module for module in catalog if module is not None
               for path in (module.get_path_name(), module.get_path_name().split('.')[0])}
    theme_id = str(theme.get_editor_property("ThemeId"))
    if expected_theme_id is not None and str(expected_theme_id).casefold() != theme_id.casefold():
        raise ValueError(f"{theme.get_path_name()}: ThemeId {theme_id} passt nicht zu {expected_theme_id}.")
    slot_ids = set()
    slots, records, corners = [], [], []
    for row in rows:
        slot = str(row.get_editor_property("SlotId")).strip()
        folded = slot.casefold()
        if not slot or folded == "none":
            raise ValueError("Ein Slot hat keine ID.")
        if folded in slot_ids:
            raise ValueError(f"Slot-ID doppelt: {slot}.")
        slot_ids.add(folded)
        original_module = row.get_editor_property("ModuleDefinition")
        module = original_module
        if slot in overrides:
            module = by_path.get(overrides[slot])
            if module is None:
                raise ValueError(f"{slot}: Das gewählte Override-Modul gehört nicht zum Theme-Katalog.")
        if module is None:
            raise ValueError(f"{slot}: Die ModuleDefinition fehlt.")
        if module not in catalog or str(module.get_editor_property("ThemeId")) != theme_id:
            raise ValueError(f"{slot}: Das Modul gehört nicht zu diesem Theme-Katalog.")
        if not module.get_editor_property("SyntyOnly"):
            raise ValueError(f"{slot}: Die ModuleDefinition verletzt SyntyOnly.")
        if str(module.get_editor_property("GeometryPolicy")) != "Rigid":
            raise ValueError(f"{slot}: Für diese Assembly ist GeometryPolicy Rigid erforderlich.")
        mesh = module.get_editor_property("StaticMeshAsset")
        if not isinstance(mesh, unreal.StaticMesh):
            raise ValueError(f"{slot}: Das Static Mesh fehlt.")
        if slot in overrides:
            original_mesh = original_module.get_editor_property("StaticMeshAsset") if original_module else None
            if not isinstance(original_mesh, unreal.StaticMesh):
                raise ValueError(f"{slot}: Die ursprüngliche Modulgeometrie fehlt.")
            original_box, replacement_box = original_mesh.get_bounding_box(), mesh.get_bounding_box()
            if any(abs(a-b) > 0.25 for side in ('min', 'max')
                   for a,b in zip(coordinates(getattr(original_box, side)),
                                  coordinates(getattr(replacement_box, side)))):
                raise ValueError(f"{slot}: Das Ersatzmodul passt nicht in die feste Modulhülle.")
        transform = row.get_editor_property("LocalTransform")
        translation = coordinates(transform.translation)
        scale = coordinates(transform.scale3d)
        quat = transform.rotation
        rotation = [quat.x, quat.y, quat.z, quat.w]
        if not all(isfinite(v) for v in translation + scale + rotation):
            raise ValueError(f"{slot}: Der lokale Transform enthält ungültige Werte.")
        if not all(abs(axis - 1.0) <= 1e-6 for axis in scale):
            raise ValueError(f"{slot}: Die Mesh-Skalierung muss 1:1 sein.")
        if abs(sum(axis * axis for axis in rotation) - 1) > 1e-5:
            raise ValueError(f"{slot}: Die lokale Rotation ist ungültig.")
        corners.extend(transformed_mesh_corners(mesh, transform))
        slots.append({"slot_id": slot, "module": module, "mesh": mesh, "local_transform": transform})
        records.append([slot, module.get_path_name(), str(module.get_editor_property("ModuleId")),
                        mesh.get_path_name(), translation, rotation, scale])

    envelope = [[min(point[axis] for point in corners) for axis in range(3)],
                [max(point[axis] for point in corners) for axis in range(3)]]
    expected = [[-size[0] / 2, -size[1] / 2, 0], [size[0] / 2, size[1] / 2, size[2]]]
    if any(abs(actual - expected[side][axis]) > 0.25
           for side in (0, 1) for axis, actual in enumerate(envelope[side])):
        raise ValueError("Die gespeicherte Hülle weicht von den transformierten Meshbounds ab.")
    payload = json.dumps([theme.get_path_name(), theme_id, size,
                          sorted(records, key=lambda record: record[0].casefold())],
                         ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {"size_cm": size, "slots": slots, "fingerprint": sha256(payload.encode()).hexdigest()}
