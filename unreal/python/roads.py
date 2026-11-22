"""Plan-scoped road and district authoring via native Actor attachments."""

from hashlib import sha256
import json
import math
from uuid import UUID, uuid5

import unreal


ACTORS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
SUBOBJECTS = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
POLYGONS = unreal.GeometryScript_PolygonList
PATHS = unreal.GeometryScript_PolyPath
SIMPLE = unreal.GeometryScript_SimplePolygon
WORLD = unreal.SplineCoordinateSpace.WORLD
ROLE = "ProofRole"
IDENTITY = "ProofId"
REVISION = "SourceRevision"
WIDTH = "RoadWidthCm"
ACCEPTED_FROM = "AcceptedProposalId"
PLAN_SCOPE = "PlanningAreaId"
LOOP_ROLE = "ProofLoop"
NAMESPACE = UUID("3e28f868-e13a-4655-9af7-ed8971540466")
MARGIN_CM2 = 1
MEMBER_ROLES = {"Road", "Proposal", "District", "KeepOut"}
PLANE_TOLERANCE_CM = 0.001
LEVEL_ROTATION_TOLERANCE_DEGREES = 0.001


def attributes(tags):
    return dict(str(tag).split("=", 1) for tag in tags if "=" in str(tag))


def metadata(actor):
    return attributes(actor.tags)


def set_metadata(actor, **values):
    preserved = [str(tag) for tag in actor.tags if str(tag).split("=", 1)[0] not in values]
    actor.modify()
    actor.set_editor_property("tags", preserved + [f"{key}={value}" for key, value in sorted(values.items())])


def actor_id(actor):
    return actor.get_editor_property("actor_guid").to_string()


def require_plan(plan):
    if not unreal.SystemLibrary.is_valid(plan) or metadata(plan).get(ROLE) != "Plan":
        raise ValueError("Kein gültiger Planungsbereich ausgewählt.")
    return actor_id(plan)


def require_member(plan, actor, role=None):
    scope = require_plan(plan)
    if not unreal.SystemLibrary.is_valid(actor):
        raise ValueError("Die Actor-Referenz des Planmitglieds fehlt.")
    data = metadata(actor)
    if (actor.get_attach_parent_actor() != plan or data.get(PLAN_SCOPE) != scope
            or data.get(ROLE) not in MEMBER_ROLES or (role and data[ROLE] != role)):
        raise ValueError(f"'{actor.get_actor_label()}' gehört nicht als {role or 'Mitglied'} zu '{plan.get_actor_label()}'.")


def members(plan, role):
    require_plan(plan)
    if role not in MEMBER_ROLES:
        raise ValueError(f"Unbekannte Planrolle '{role}'.")
    found = {}
    for actor in plan.get_attached_actors():
        data = metadata(actor)
        if data.get(ROLE) != role:
            continue
        require_member(plan, actor, role)
        key = data.get(IDENTITY)
        if not key:
            raise ValueError(f"'{actor.get_actor_label()}' hat keine gespeicherte Mitglieds-ID.")
        if key in found:
            raise ValueError(f"Doppelte Mitglieds-ID '{key}' in '{plan.get_actor_label()}'.")
        found[key] = actor
    return found


def attach_member(plan, actor, role, **extra):
    scope = require_plan(plan)
    if not unreal.SystemLibrary.is_valid(actor):
        raise ValueError("Die Actor-Referenz des zuzuordnenden Planmitglieds fehlt.")
    if actor == plan or role not in MEMBER_ROLES or metadata(actor).get(ROLE) == "Plan":
        raise ValueError("Nur Straßen, Vorschläge, Distrikte und Freihalteflächen können zugeordnet werden.")
    current = actor.get_attach_parent_actor()
    if current or metadata(actor).get(PLAN_SCOPE):
        owner = current.get_actor_label() if current else metadata(actor)[PLAN_SCOPE]
        raise ValueError(f"'{actor.get_actor_label()}' ist bereits '{owner}' zugeordnet.")
    if actor.get_outer() != plan.get_outer():
        raise ValueError("Plan und Mitglied müssen im selben Level liegen.")
    rule = unreal.AttachmentRule.KEEP_WORLD
    if not actor.attach_to_actor(plan, "", rule, rule, rule, False):
        raise ValueError(f"'{actor.get_actor_label()}' konnte nicht am Plan befestigt werden.")
    try:
        set_metadata(actor, **{ROLE: role, IDENTITY: actor_id(actor), PLAN_SCOPE: scope, **extra})
    except Exception:
        rule = unreal.DetachmentRule.KEEP_WORLD
        actor.detach_from_actor(rule, rule, rule)
        raise
    require_member(plan, actor, role)
    return actor


def plan_for(actor):
    if not unreal.SystemLibrary.is_valid(actor):
        raise ValueError("Keine gültige Actor-Referenz ausgewählt.")
    if metadata(actor).get(ROLE) == "Plan":
        require_plan(actor)
        return actor
    plan = actor.get_attach_parent_actor()
    require_member(plan, actor)
    return plan


def keepouts(plan):
    return members(plan, "KeepOut")


def vectors(points):
    return [unreal.Vector(*point) for point in points]


def vec_data(vec):
    return [round(value, 6) for value in vec.to_tuple()]


def set_points(component, points, closed, space=WORLD):
    component.modify()
    component.set_spline_points(vectors(points), space, False)
    for index, _ in enumerate(points):
        component.set_spline_point_type(index, unreal.SplinePointType.LINEAR, False)
    component.set_closed_loop(closed, True)
    component.set_editor_property("spline_has_been_edited", True)


def new_loop(actor, loop_role, points, closed):
    handles = SUBOBJECTS.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=unreal.SplineComponent)
    handle, reason = SUBOBJECTS.add_new_subobject(params)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    assert lib.is_handle_valid(handle), reason
    component = lib.get_associated_object(lib.get_data(handle))
    assert isinstance(component, unreal.SplineComponent)
    component.set_editor_property("component_tags", [f"{LOOP_ROLE}={loop_role}"])
    set_points(component, points, closed)
    return component


def loops(actor):
    components = actor.get_components_by_class(unreal.SplineComponent)
    if len(components) == 1 and LOOP_ROLE not in attributes(components[0].component_tags):
        role = "path" if metadata(actor).get(ROLE) == "Road" else "outer"
        return {role: components[0]}
    return {attributes(component.component_tags)[LOOP_ROLE]: component for component in components}


def spawn(role, label, rings, closed=True, *, plan=None, identity=None, **extra):
    if role != "Plan":
        require_plan(plan)
    actor = ACTORS.spawn_actor_from_class(unreal.Actor, unreal.Vector())
    try:
        actor.set_actor_label(label)
        for name, control_points in rings.items():
            new_loop(actor, name, control_points, closed)
        if role == "Plan":
            set_metadata(actor, **{ROLE: role, **extra})
            return actor
        if identity is not None:
            extra[IDENTITY] = identity
        return attach_member(plan, actor, role, **extra)
    except Exception:
        ACTORS.destroy_actor(actor)
        raise


def points(component):
    return [vec_data(component.get_location_at_spline_point(index, WORLD))
            for index in range(component.get_number_of_spline_points())]


def sampling():
    options = unreal.GeometryScriptSplineSamplingOptions()
    options.coordinate_space = WORLD
    options.sample_spacing = unreal.GeometryScriptSampleSpacing.ERROR_TOLERANCE
    options.error_tolerance = 1.0
    return options


def area(polygons):
    return POLYGONS.get_polygon_list_area(polygons)


def plan_elevation(plan):
    require_plan(plan)
    rotation = plan.get_actor_rotation()
    if (abs(rotation.pitch) > LEVEL_ROTATION_TOLERANCE_DEGREES
            or abs(rotation.roll) > LEVEL_ROTATION_TOLERANCE_DEGREES):
        raise ValueError(f"'{plan.get_actor_label()}' braucht eine horizontale Planungsebene.")
    return plan.get_actor_location().z


def planar_path(actor, component, closed, elevation):
    if component.is_closed_loop() != closed:
        shape = "geschlossenen" if closed else "offenen"
        raise ValueError(f"'{actor.get_actor_label()}' braucht einen {shape} Spline.")
    path = PATHS.convert_spline_to_poly_path(component, sampling())
    sampled_points = [vec_data(point) for point in PATHS.convert_poly_path_to_array(path)]
    if len(sampled_points) < (3 if closed else 2) or any(
            abs(point[2] - elevation) > PLANE_TOLERANCE_CM for point in sampled_points):
        raise ValueError(f"'{actor.get_actor_label()}' muss vollständig auf der Planebene Z={elevation:g} liegen.")
    return path, sampled_points


def actor_polygon(actor):
    native_loops = loops(actor)
    outer = native_loops.pop("outer", None)
    if outer is None:
        raise ValueError(f"'{actor.get_actor_label()}' braucht einen Außenspline.")
    elevation = plan_elevation(plan_for(actor))
    for component in [outer, *native_loops.values()]:
        planar_path(actor, component, closed=True, elevation=elevation)
    opts = sampling()
    return POLYGONS.create_polygon_list_from_single_polygon(
        SIMPLE.convert_spline_to_polygon(outer, opts),
        [SIMPLE.convert_spline_to_polygon(component, opts) for component in native_loops.values()],
    )


def road_path(actor):
    component = loops(actor).get("path")
    if component is None:
        raise ValueError(f"'{actor.get_actor_label()}' braucht einen Straßenspline.")
    elevation = plan_elevation(plan_for(actor))
    sampled, sampled_points = planar_path(actor, component, closed=False, elevation=elevation)
    try:
        width = float(actor.get_editor_property(WIDTH))
    except Exception:
        width = float(metadata(actor).get(WIDTH, 0))
    if not math.isfinite(width) or width <= 0:
        raise ValueError(f"'{actor.get_actor_label()}' braucht eine positive Breite.")
    return width, sampled, sampled_points


def corridor(path, width):
    options = unreal.GeometryScriptOpenPathOffsetOptions()
    options.end_type = unreal.GeometryScriptPathOffsetEndType.BUTT
    options.join_type = unreal.GeometryScriptPolyOffsetJoinType.ROUND
    occupied, success = POLYGONS.create_polygons_from_open_poly_paths_offset(
        [path], options, width, False
    )
    assert success and POLYGONS.get_polygon_count(occupied) == 1
    return occupied


def digest(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def canonical(ring):
    # Rotation and winding of a native ring do not define its proposal identity.
    flat = [tuple(round(value, 4) for value in point[:2]) for point in ring]
    assert len(flat) >= 3 and len(flat) == len(set(flat)), flat
    reverse = list(reversed(flat))
    return min(tuple(order[index:] + order[:index])
               for order in (flat, reverse) for index in range(len(order)))


def solve(plan):
    plan_identity = require_plan(plan)
    elevation = plan_elevation(plan)
    plan_polygon = actor_polygon(plan)
    source_paths = []
    road_masks = unreal.GeometryScriptGeneralPolygonList()
    for key, road in sorted(members(plan, "Road").items()):
        width, path, vertices = road_path(road)
        source_paths.append({"id": key, "width_cm": width, "samples": vertices})
        road_masks = POLYGONS.append_polygon_list(road_masks, corridor(path, width))
    occupied = POLYGONS.polygons_union(road_masks, False)
    free = POLYGONS.polygons_difference(plan_polygon, occupied)
    recipe = {"plan_id": plan_identity, "plan_elevation_cm": elevation,
              "plan_loops": {name: planar_path(plan, component, True, elevation)[1]
                             for name, component in loops(plan).items()},
              "sampling_error_cm": 1, "roads": source_paths}
    revision = digest(recipe)
    proposals = {}
    for index in range(POLYGONS.get_polygon_count(free)):
        holes, valid = POLYGONS.get_polygon_hole_count(free, index)
        assert valid
        rings = {}
        native_rings = []
        for hole in range(-1, holes):
            simple, _ = POLYGONS.get_simple_polygon(free, index, hole)
            vertices = SIMPLE.conv_geometry_script_simple_polygon_to_array_of_vector2d(simple)
            # UE 5.8.1 GetSimplePolygon writes false even on a successful read.
            count, valid = POLYGONS.get_polygon_vertex_count(free, index, hole)
            assert valid and len(vertices) == count >= 3, (index, hole, len(vertices), count)
            native_rings.append(simple)
            rings["outer" if hole < 0 else f"hole{hole+1}"] = [
                [point.x, point.y, elevation]
                for point in vertices
            ]
        footprint = POLYGONS.create_polygon_list_from_single_polygon(native_rings[0], native_rings[1:])
        key = digest([plan_identity, canonical(rings["outer"]), sorted(
            canonical(ring) for name, ring in rings.items() if name != "outer"
        )])
        proposal_id = str(uuid5(NAMESPACE, "Proposal/" + key))
        assert proposal_id not in proposals
        proposals[proposal_id] = {"polygon": footprint, "rings": rings, "holes": holes, "plan_id": plan_identity,
                                  "area_m2": round(area(footprint)/10_000, 5)}
    return revision, recipe, proposals


def proposal_summary(proposals):
    return {key: {"area_m2": value["area_m2"], "holes": value["holes"]}
            for key, value in sorted(proposals.items())}


def reconcile(plan, revision, proposals):
    scope = require_plan(plan)
    if any(item.get("plan_id") != scope for item in proposals.values()):
        raise ValueError("Vorschläge eines anderen Plans können hier nicht angewendet werden.")
    current = members(plan, "Proposal")
    ordered = sorted(proposals, key=lambda key: min(point[1] for point in proposals[key]["rings"]["outer"]))
    for index, proposal_id in enumerate(ordered, 1):
        if proposal_id in current:
            actor = current.pop(proposal_id)
            if metadata(actor)[REVISION] != revision:
                set_metadata(actor, **{**metadata(actor), REVISION: revision})
        else:
            actor = spawn("Proposal", f"Distriktvorschlag {index}", proposals[proposal_id]["rings"],
                          plan=plan, identity=proposal_id, **{REVISION: revision})
        difference = POLYGONS.polygons_exclusive_or(actor_polygon(actor), proposals[proposal_id]["polygon"])
        assert abs(area(difference)) < MARGIN_CM2, proposal_id
    for actor in current.values():
        assert ACTORS.destroy_actor(actor)
    assert len(members(plan, "Proposal")) == len(proposals)


def accept(plan, proposal, name):
    require_member(plan, proposal, "Proposal")
    data = metadata(proposal)
    proposal_id = data[IDENTITY]
    identity = str(uuid5(NAMESPACE, f"Accepted/{data[PLAN_SCOPE]}/{proposal_id}"))
    districts = members(plan, "District")
    if identity in districts:
        assert metadata(districts[identity])[ACCEPTED_FROM] == proposal_id
        return districts[identity]
    shape = actor_polygon(proposal)
    conflicting_districts = sorted(
        key for key, actor in districts.items()
        if area(POLYGONS.polygons_intersection(shape, actor_polygon(actor))) > MARGIN_CM2
    )
    if conflicting_districts:
        raise ValueError("Assign overlapping proposal to existing district(s): " + ", ".join(conflicting_districts))
    rings = {name: points(component) for name, component in loops(proposal).items()}
    return spawn("District", name, rings, plan=plan, identity=identity, **{
        REVISION: data[REVISION], ACCEPTED_FROM: proposal_id,
    })


def snapshots(plan, role):
    result = {}
    for key, actor in members(plan, role).items():
        data = metadata(actor)
        rotation = actor.get_actor_rotation()
        assert key not in result
        result[key] = {
            "id": key,
            "name": actor.get_actor_label(),
            "guid": actor.get_editor_property("actor_guid").to_string(),
            "origin_cm": vec_data(actor.get_actor_location()),
            "rotation_degrees": [rotation.roll, rotation.pitch, rotation.yaw],
            "tags": data,
            "loops": {
                name: {"closed": component.is_closed_loop(), "points": points(component)}
                for name, component in loops(actor).items()
            },
        }
    return result


def rectangle(min_x, min_y, max_x, max_y):
    vertices = [unreal.Vector2D(x, y) for x, y in (
        (min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y),
    )]
    shape = SIMPLE.conv_array_of_vector2d_to_geometry_script_simple_polygon(vertices)
    return POLYGONS.create_polygon_list_from_single_polygon(shape, [])


def available_districts(plan):
    _, _, proposals = solve(plan)
    free = unreal.GeometryScriptGeneralPolygonList()
    for proposal in proposals.values():
        free = POLYGONS.append_polygon_list(free, proposal["polygon"])
    free = POLYGONS.polygons_union(free, False)
    return {key: POLYGONS.polygons_intersection(actor_polygon(actor), free)
            for key, actor in members(plan, "District").items()}


def plan_grid(plan):
    require_plan(plan)
    boundary = loops(plan)["outer"]
    planar_path(plan, boundary, closed=True, elevation=plan_elevation(plan))
    transform = plan.get_actor_transform()
    math_api = unreal.MathLibrary
    coordinates = [vec_data(math_api.inverse_transform_location(transform, point))
                   for point in vectors(points(boundary))]
    lo_x, hi_x = min(point[0] for point in coordinates), max(point[0] for point in coordinates)
    lo_y, hi_y = min(point[1] for point in coordinates), max(point[1] for point in coordinates)
    return [tuple(vec_data(math_api.transform_location(transform, unreal.Vector(x, y, 0))))
            for y in range(int(lo_y + 750), int(hi_y), 1500)
            for x in range(int(lo_x + 1100), int(hi_x), 2200)]
