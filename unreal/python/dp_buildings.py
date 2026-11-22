"""Plan-scoped editor actions for native rectangular building sources."""

from math import isfinite

import unreal

import roads
from dp_fixed_assembly import load_assembly


CLASS_PATH = ("/Game/DeltaPoly/PCG/Buildings/Blueprints/BP_DP_BLD_BuildingBinding"
              ".BP_DP_BLD_BuildingBinding_C")
SOURCE = "DP.NativeBlockoutSource"
MANUAL = "DP.ManualBuildingExclusion"
STAGED = "DP.StagedBuildingDetail"
DETAIL = "DP.PublishedBuildingDetail"
OWNER = "DP.BuildingOwner:"
SLOT = "DP.AssemblySlot:"
FINGERPRINT = "DP.AssemblyFingerprint:"
CUBE = unreal.load_asset("/Engine/BasicShapes/Cube.Cube")
ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EPSILON_CM = 0.25


def tags(actor):
    return {str(tag) for tag in actor.get_editor_property("Tags")}


def set_tags(actor, *markers):
    actor.set_editor_property("Tags", list(markers))


def owned_id(binding):
    stamp = binding.get_editor_property("BindingId")
    if not stamp or stamp != roads.actor_id(binding):
        raise ValueError("Die BindingId fehlt oder gehört einem anderen Actor.")
    return stamp


def visibility(actor, shown):
    component = actor.static_mesh_component
    changed = component.is_visible() != shown or actor.get_actor_enable_collision() != shown
    if changed:
        actor.modify()
        component.modify()
        component.set_visibility(shown, False)
        actor.set_actor_enable_collision(shown)
    return changed


def bounds(actor):
    return [roads.vec_data(vector) for vector in actor.get_actor_bounds(False)]


def spawn_mesh(mesh, location, scale, label, role, rotation=None, shown=True):
    actor = ACTORS.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(*location), rotation or unreal.Rotator(),
    )
    if actor is None:
        raise RuntimeError("Static Mesh Actor konnte nicht erzeugt werden.")
    actor.set_actor_label(label)
    set_tags(actor, role)
    actor.set_actor_scale3d(unreal.Vector(*scale))
    actor.static_mesh_component.set_static_mesh(mesh)
    visibility(actor, shown)
    return actor


def _inherit_editor_placement(actor, owner):
    """Keep linked actors in the same editor folder and World Partition loading scope."""
    actor.set_folder_path(owner.get_folder_path())
    actor.set_editor_property("is_spatially_loaded", owner.get_editor_property("is_spatially_loaded"))


def scene_bindings(plan):
    cls = unreal.load_object(None, CLASS_PATH)
    return {
        owned_id(actor): actor
        for district in roads.members(plan, "District").values()
        for actor in district.get_attached_actors()
        if actor.get_attach_parent_actor() == district and actor.get_class() == cls
        and actor.get_editor_property("BindingId") == roads.actor_id(actor)
    }


def district_for(plan, binding):
    owned_id(binding)
    district = binding.get_attach_parent_actor()
    roads.require_member(plan, district, "District")
    return district


def owned_details(binding):
    expected = {DETAIL, OWNER + owned_id(binding)}
    published = list(binding.get_editor_property("PublishedDetailActors"))
    actor_ids, slot_ids = set(), set()
    for actor in published:
        if not unreal.SystemLibrary.is_valid(actor):
            raise ValueError("Eine publizierte Detailreferenz fehlt.")
        actor_tags = tags(actor)
        slots = [tag[len(SLOT):] for tag in actor_tags if tag.startswith(SLOT)]
        key = roads.actor_id(actor)
        if (not expected <= actor_tags or len(slots) != 1 or not slots[0] or
                slots[0] in slot_ids or key in actor_ids):
            raise ValueError("Die Besitzer- oder Slotreferenzen der Detailausgabe sind widersprüchlich.")
        actor_ids.add(key)
        slot_ids.add(slots[0])
    return published


def footprint(actor):
    if (isinstance(actor, unreal.StaticMeshActor) and SOURCE in tags(actor)
            and actor.static_mesh_component.static_mesh == CUBE):
        transform = actor.get_actor_transform()
        corners = [transform.transform_location(unreal.Vector(x, y, -50))
                   for x, y in ((-50, -50), (50, -50), (50, 50), (-50, 50))]
        shape = roads.SIMPLE.conv_array_of_vector2d_to_geometry_script_simple_polygon(
            [unreal.Vector2D(point.x, point.y) for point in corners])
        return roads.POLYGONS.create_polygon_list_from_single_polygon(shape, [])
    (x, y, _), (half_x, half_y, _) = bounds(actor)
    return roads.rectangle(x - half_x, y - half_y, x + half_x, y + half_y)


def stage_slot_selection(plan, selected_outputs, module=None):
    """Store a validated explicit slot choice; regeneration remains a separate action."""
    selected = set(selected_outputs)
    if not selected:
        raise ValueError("Mindestens ein erzeugtes Gebäudemodul auswählen.")
    bindings = scene_bindings(plan)
    owners = {}
    for key, binding in bindings.items():
        for actor in binding.get_editor_property("PublishedDetailActors"):
            if actor not in selected:
                continue
            if actor in owners:
                raise ValueError("Ein Ausgabemodul ist mehreren Gebäuden zugeordnet.")
            owners[actor] = (key, binding)
    if selected - owners.keys():
        raise ValueError("Nur registrierte Detailmodule dieses Plans auswählen, keine Blockformen oder Kopien.")
    prepared = {}
    for actor in selected:
        key, binding = owners[actor]
        if key not in prepared:
            owned_details(binding)
            original = dict(binding.get_editor_property("SlotModuleOverrides"))
            prepared[key] = (binding, original, dict(original), [])
        _, _, desired, slots = prepared[key]
        slot = next(tag[len(SLOT):] for tag in tags(actor) if tag.startswith(SLOT))
        slots.append(slot)
        if module is None:
            desired.pop(slot, None)
        else:
            path = module.get_path_name()
            if desired.get(slot) not in (path, path.split('.')[0]):
                desired[slot] = path
    # Validate the entire selection before changing even one persistent map.
    for binding, _, desired, _ in prepared.values():
        original = dict(binding.get_editor_property("SlotModuleOverrides"))
        for slot in binding.get_editor_property("LockedSlotIds"):
            if slot in original and desired.get(slot) != original[slot]:
                raise ValueError(f"{slot}: Die Modulauswahl ist gesperrt. Vor dem Ändern oder Zurücksetzen entsperren.")
        load_assembly(binding.get_editor_property("ThemeDefinition"), slot_overrides=desired)
    with unreal.ScopedEditorTransaction("DP Gebäudemodulauswahl vormerken"):
        try:
            for binding, original, desired, _ in prepared.values():
                if desired != original:
                    binding.modify()
                    binding.set_editor_property("SlotModuleOverrides", desired)
        except Exception:
            for binding, original, _, _ in prepared.values():
                binding.set_editor_property("SlotModuleOverrides", original)
            raise
    return {key: {"decision": "override_staged" if original != desired else "unchanged",
                  "slots": sorted(slots)}
            for key, (_, original, desired, slots) in prepared.items()}


def source_geometry_hash(source):
    rotation = source.get_actor_rotation().quaternion()
    return roads.digest([roads.actor_id(source), roads.vec_data(source.get_actor_location()),
                         [50 * value for value in roads.vec_data(source.get_actor_scale3d())],
                         [rotation.x, rotation.y, rotation.z, rotation.w]])


def reservations(plan, bindings):
    reserved = [
        ("reserved_area", roads.actor_polygon(actor), actor) for actor in roads.keepouts(plan).values()
    ] + [
        ("manual_footprint", footprint(actor), actor) for actor in plan.get_attached_actors()
        if actor.get_attach_parent_actor() == plan and MANUAL in tags(actor)
    ] + [
        ("existing_source", footprint(source), source) for binding in bindings.values()
        if unreal.SystemLibrary.is_valid(source := binding.get_editor_property("NativeBlockoutSource"))
    ]
    for binding in bindings.values():
        source = binding.get_editor_property("NativeBlockoutSource")
        source_valid = unreal.SystemLibrary.is_valid(source)
        if source_valid and binding.get_editor_property("SourceGeometryHash") == source_geometry_hash(source):
            continue
        occupied = unreal.GeometryScriptGeneralPolygonList()
        expected = {DETAIL, OWNER + owned_id(binding)}
        for actor in binding.get_editor_property("PublishedDetailActors"):
            if not unreal.SystemLibrary.is_valid(actor) or not expected <= tags(actor):
                continue
            if actor.static_mesh_component.is_visible() or actor.get_actor_enable_collision():
                occupied = roads.POLYGONS.append_polygon_list(occupied, footprint(actor))
        if roads.area(occupied) > roads.MARGIN_CM2:
            # Old output remains physically present until its source update succeeds.
            # Its module bounds are conservative; release follows an explicit update.
            reserved.append(("existing_output", roads.POLYGONS.polygons_union(occupied, False),
                             source if source_valid else binding))
    return reserved


def assess_footprint(polygon, allowed, avoid, own_source=None):
    excess = roads.area(roads.POLYGONS.polygons_difference(polygon, allowed))
    if excess > roads.MARGIN_CM2:
        return {"decision": "outside_district_or_road_hole", "overlap_cm2": round(excess, 4)}
    for decision, blocked, actor in avoid:
        if actor != own_source:
            overlap = roads.area(roads.POLYGONS.polygons_intersection(polygon, blocked))
            if overlap > roads.MARGIN_CM2:
                return {"decision": decision, "overlap_cm2": round(overlap, 4)}
    return {"decision": "fits"}


def _new_building(plan, district, center, size, theme, label):
    ground = (center[0], center[1], center[2] + size[2] / 2)
    source = spawn_mesh(CUBE, ground, [axis / 100 for axis in size], label + " · Blockform", SOURCE)
    roads.set_metadata(source, **{roads.PLAN_SCOPE: roads.require_plan(plan)})
    binding = None
    try:
        _inherit_editor_placement(source, district)
        binding = ACTORS.spawn_actor_from_class(unreal.load_object(None, CLASS_PATH), unreal.Vector(*ground))
        binding.set_actor_label(label + " · Binding")
        _inherit_editor_placement(binding, district)
        keep = unreal.AttachmentRule.KEEP_WORLD
        if not binding.attach_to_actor(district, "", keep, keep, keep, False):
            raise RuntimeError("Binding ließ sich nicht dem Distrikt zuordnen.")
        binding.set_editor_properties({
            "BindingId": roads.actor_id(binding), "NativeBlockoutSource": source,
            "ThemeDefinition": theme, "ThemeId": theme.get_editor_property("ThemeId"),
        })
        if binding.get_editor_property("DetailsEnabled") or owned_details(binding):
            raise RuntimeError("Neue Gebäude müssen im Blockform-Modus beginnen.")
    except Exception:
        if unreal.SystemLibrary.is_valid(binding):
            ACTORS.destroy_actor(binding)
        ACTORS.destroy_actor(source)
        raise
    return binding


def generate_blockouts(plan, theme, *, district_ids, count_per_district=2):
    selected = set(district_ids)
    districts = roads.members(plan, "District")
    if not selected or selected - districts.keys() or count_per_district < 1:
        raise ValueError("Angenommene Distrikte dieses Plans und eine gültige Zielzahl wählen.")
    size = load_assembly(theme)["size_cm"]
    width, depth, _ = size
    available = roads.available_districts(plan)
    existing = scene_bindings(plan)
    avoid = reservations(plan, existing)
    grid = roads.plan_grid(plan)
    result = {}
    for key in sorted(selected):
        district = districts[key]
        count = sum(actor.get_attach_parent_actor() == district for actor in existing.values())
        created, rejected = [], []
        for center in grid if count < count_per_district else ():
            x, y, _ = center
            rectangle = roads.rectangle(x - width / 2, y - depth / 2, x + width / 2, y + depth / 2)
            decision = assess_footprint(rectangle, available[key], avoid)
            if decision["decision"] != "fits":
                rejected.append({"center_cm": center, **decision})
                continue
            count += 1
            actor = _new_building(plan, district, center, size, theme,
                                  f"{district.get_actor_label()} · Haus {count}")
            created.append(owned_id(actor))
            source = actor.get_editor_property("NativeBlockoutSource")
            avoid.append(("existing_source", footprint(source), source))
            if count == count_per_district:
                break
        result[key] = {"created": created, "rejected": rejected, "unfilled": max(0, count_per_district - count)}
    return result


def _selected(plan, *, building_ids, district_ids):
    buildings, districts = scene_bindings(plan), roads.members(plan, "District")
    ids, areas = set(building_ids), set(district_ids)
    if not (ids or areas) or ids - buildings.keys() or areas - districts.keys():
        raise ValueError("Gebäude und Distrikte müssen ausdrücklich aus demselben Plan gewählt werden.")
    chosen = {districts[key] for key in areas}
    ids.update(key for key, actor in buildings.items() if actor.get_attach_parent_actor() in chosen)
    return {key: buildings[key] for key in sorted(ids)}, buildings


def native_source_geometry(plan, binding):
    """Return an upright Cube source, world center and unrotated half sizes."""
    label = binding.get_actor_label()
    source = binding.get_editor_property("NativeBlockoutSource")
    if (not unreal.SystemLibrary.is_valid(source) or not isinstance(source, unreal.StaticMeshActor) or
            SOURCE not in tags(source) or roads.metadata(source).get(roads.PLAN_SCOPE) != roads.require_plan(plan)
            or source.static_mesh_component.static_mesh != CUBE):
        raise ValueError(f"{label}: Eine eigene Cube-Quellform dieses Plans muss zugewiesen sein.")
    rotation = source.get_actor_rotation()
    if (not all(isfinite(value) for value in (rotation.pitch, rotation.roll, rotation.yaw)) or
            max(abs(rotation.pitch), abs(rotation.roll)) >= 0.001):
        raise ValueError(f"{label}: Die Cube-Quellform darf nur um die Hochachse gedreht werden.")
    location = roads.vec_data(source.get_actor_location())
    half = [50 * value for value in roads.vec_data(source.get_actor_scale3d())]
    if (not all(isfinite(value) and value > 0 for value in half) or
            not all(isfinite(value) for value in location) or
            abs(location[2] - half[2] - roads.plan_elevation(plan)) > EPSILON_CM):
        raise ValueError(f"{label}: Die Cube-Quellform muss auf der Planebene stehen.")
    return source, location, half


def _prepare(plan, binding, assemblies, source_counts, *, require_details=True):
    label = binding.get_actor_label()
    source, location, half = native_source_geometry(plan, binding)
    if source_counts[source] != 1:
        raise ValueError(f"{label}: Eine eigene Cube-Quellform dieses Plans muss zugewiesen sein.")
    previous = owned_details(binding)
    theme = binding.get_editor_property("ThemeDefinition")
    if not require_details:
        return source, location, half, theme, None, previous
    unsupported = [description for field, description in (
        ("FloorCountOverride", "freie Geschosszahl"),
        ("RegionThemeOverrides", "Stilwechsel einzelner Gebäuderegionen"),
        ("OverrideSurfaceStyle", "eigener Oberflächenstil"),
        ("OverrideBuildingColor", "eigene Gebäudefarbe"),
    ) if binding.get_editor_property(field)]
    if unsupported:
        raise ValueError(f"{label}: Die feste Gebäudevorlage unterstützt noch nicht: " +
                         ", ".join(unsupported) + ". Diese Overrides deaktivieren; vorhandene Ausgabe bleibt erhalten.")
    try:
        overrides = dict(binding.get_editor_property("SlotModuleOverrides"))
        locked = set(binding.get_editor_property("LockedSlotIds"))
        if unresolved := locked - overrides.keys():
            raise ValueError("Gesperrte Slots ohne gespeicherte Modulauswahl: " + ", ".join(sorted(unresolved)) +
                             ". Auswahl zuordnen oder Sperre bewusst entfernen.")
        assembly_key = (theme, tuple(sorted(overrides.items())))
        if assembly_key not in assemblies:
            assemblies[assembly_key] = load_assembly(theme, slot_overrides=overrides)
        assembly = assemblies[assembly_key]
    except ValueError as error:
        raise ValueError(f"{label}: {error}") from error
    return source, location, half, theme, assembly, previous


def _publish(binding, data):
    source, location, half, theme, assembly, previous = data
    if any(abs(2 * extent - size) > EPSILON_CM for extent, size in zip(half, assembly["size_cm"])):
        return {"decision": "kit_does_not_fit"}
    owner = owned_id(binding)
    theme_id = theme.get_editor_property("ThemeId")
    rotation = source.get_actor_rotation().quaternion()
    geometry = source_geometry_hash(source)
    fingerprint = FINGERPRINT + roads.digest([geometry, assembly["fingerprint"]])
    expected_slots = {SLOT + slot["slot_id"] for slot in assembly["slots"]}
    previous_slots = {tag for output in previous for tag in tags(output) if tag.startswith(SLOT)}
    if (binding.get_editor_property("ThemeId") == theme_id and
            previous_slots == expected_slots and all(fingerprint in tags(actor) for actor in previous)):
        changed = not binding.get_editor_property("DetailsEnabled")
        for actor in previous:
            changed = visibility(actor, True) or changed
        changed = visibility(source, False) or changed
        if changed:
            binding.modify()
            binding.set_editor_property("DetailsEnabled", True)
            return {"decision": "published", "module_count": len(previous)}
        return {"decision": "unchanged"}
    changed = binding.get_editor_property("SourceGeometryHash") != geometry
    if changed and not binding.call_method("NeedsSourceRebuild", (geometry,)):
        return {"decision": "source_rebuild_disabled"}

    base = [location[0], location[1], location[2] - half[2]]
    placement = unreal.Transform(location=base, rotation=rotation.rotator())
    staged = []
    try:
        for row in assembly["slots"]:
            transform = row["local_transform"]
            location_cm = roads.vec_data(placement.transform_location(transform.translation))
            world_rotation = (rotation * transform.rotation).rotator()
            actor = spawn_mesh(row["mesh"], location_cm, roads.vec_data(transform.scale3d),
                               row["slot_id"], STAGED, world_rotation, shown=False)
            staged.append(actor)
            _inherit_editor_placement(actor, binding)
            if actor.static_mesh_component.static_mesh != row["mesh"]:
                raise RuntimeError("Das Detailmesh konnte nicht zugewiesen werden.")
    except Exception:
        for actor in staged:
            ACTORS.destroy_actor(actor)
        raise

    if changed:
        revision = binding.get_editor_property("SourceRevision")
        binding.modify()
        binding.call_method("CommitSourceRevision", (geometry,))
        assert binding.get_editor_property("SourceGeometryHash") == geometry
        assert binding.get_editor_property("SourceRevision") == revision + 1
    for row, actor in zip(assembly["slots"], staged):
        set_tags(actor, DETAIL, OWNER + owner, SLOT + row["slot_id"], fingerprint)
        visibility(actor, True)
    binding.set_editor_properties({
        "DetailsEnabled": True, "PublishedDetailActors": staged, "ThemeId": theme_id,
    })
    for actor in previous:
        assert ACTORS.destroy_actor(actor)
    visibility(source, False)
    return {"decision": "published", "module_count": len(staged)}


def _apply_selected(plan, building_ids, district_ids, *, activate):
    selected, bindings = _selected(plan, building_ids=building_ids, district_ids=district_ids)
    available = roads.available_districts(plan)
    counts = {}
    binding_class = unreal.load_object(None, CLASS_PATH)
    for actor in ACTORS.get_all_level_actors():
        if actor.get_class() != binding_class or actor.get_editor_property("BindingId") != roads.actor_id(actor):
            continue
        source = actor.get_editor_property("NativeBlockoutSource")
        if source is not None:
            counts[source] = counts.get(source, 0) + 1
    assemblies = {}
    prepared = {key: _prepare(plan, actor, assemblies, counts,
                              require_details=activate or actor.get_editor_property("DetailsEnabled"))
                for key, actor in selected.items()}
    excluded = reservations(plan, bindings)
    decisions = {}
    for key, binding in selected.items():
        if not activate and not binding.get_editor_property("DetailsEnabled"):
            source, *_, previous = prepared[key]
            changed = visibility(source, True)
            for actor in previous:
                changed = visibility(actor, False) or changed
            decisions[key] = {"decision": "deactivated" if changed else "inactive"}
            continue
        source = prepared[key][0]
        district = roads.metadata(district_for(plan, binding))[roads.IDENTITY]
        assessment = assess_footprint(footprint(source), available[district], excluded, own_source=source)
        decisions[key] = _publish(binding, prepared[key]) if assessment["decision"] == "fits" else assessment
    return decisions


def activate_details(plan, *, building_ids=(), district_ids=()):
    return _apply_selected(plan, building_ids, district_ids, activate=True)


def update_selection(plan, *, building_ids=(), district_ids=()):
    return _apply_selected(plan, building_ids, district_ids, activate=False)


def cleanup_details(plan, *, building_ids=(), district_ids=()):
    """Remove only registered output, preserving sources and authored overrides."""
    selected, _ = _selected(plan, building_ids=building_ids, district_ids=district_ids)
    # Validate the complete selection before removing any output.
    prepared = {key: (native_source_geometry(plan, binding)[0], owned_details(binding))
                for key, binding in selected.items()}
    binding_class = unreal.load_object(None, CLASS_PATH)
    sources = [actor.get_editor_property("NativeBlockoutSource")
               for actor in ACTORS.get_all_level_actors()
               if actor.get_class() == binding_class and
               actor.get_editor_property("BindingId") == roads.actor_id(actor)]
    if any(sources.count(source) != 1 for source, _ in prepared.values()):
        raise ValueError("Eine Quellform wird von mehreren Gebäuden verwendet; Bereinigung abgewiesen.")
    decisions = {}
    with unreal.ScopedEditorTransaction("Bereinigte Gebäudedetails"):
        for key, binding in selected.items():
            source, previous = prepared[key]
            changed = bool(previous) or bool(binding.get_editor_property("DetailsEnabled"))
            changed = changed or not source.static_mesh_component.is_visible() or not source.get_actor_enable_collision()
            if changed:
                binding.modify()
                for actor in previous:
                    if not ACTORS.destroy_actor(actor):
                        # Keep remaining refs discoverable if an editor deletion fails.
                        binding.set_editor_property("PublishedDetailActors", [
                            item for item in previous if unreal.SystemLibrary.is_valid(item)])
                        raise ValueError("Ein Gebäudemodul konnte nicht entfernt werden; Bereinigung unvollständig. "
                                         "Verbleibende Details und der bisherige Blockform-Modus bleiben erhalten.")
                binding.set_editor_properties({"PublishedDetailActors": [], "DetailsEnabled": False})
                visibility(source, True)
            decisions[key] = {"decision": "cleaned" if changed else "unchanged", "removed_count": len(previous)}
    return decisions
