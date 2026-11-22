"""Publish plan-scoped exclusion splines for native PCG vegetation graphs."""

from math import isfinite

import unreal

import dp_buildings as buildings
import roads


CLEARANCE = "VegetationClearance"
ALL = "All"
WOODY = "Woody"
_CATEGORY_TAGS = {ALL: "DP_MaskGround", WOODY: "DP_MaskWoody"}
_OWNER = "DPVegetationMaskOwner"
_COMPONENT = "DPVegetationMaskComponent"
_PROVIDER = "DPVegetationMaskProvider"
_POLYGONS = roads.POLYGONS


def _outer_ring(polygon, index, elevation):
    count, valid = _POLYGONS.get_polygon_vertex_count(polygon, index, -1)
    vertices, _ = _POLYGONS.get_polygon_vertices(polygon, index, -1)
    # The vertex getter always reports false in UE 5.8.1.
    if not valid or len(vertices) != count or count < 3:
        raise ValueError("Der Maskenring konnte nicht gelesen werden.")
    return [roads.vec_data(unreal.Vector(point.x, point.y, elevation)) for point in vertices]


def _spline_rings(polygon, elevation):
    count = _POLYGONS.get_polygon_count(polygon)
    area = roads.area(polygon)
    if not count or not isfinite(area) or area <= 0:
        raise ValueError("Die Vegetationsmaske braucht eine Fläche.")
    hole_counts = [_POLYGONS.get_polygon_hole_count(polygon, index) for index in range(count)]
    if not all(valid for _, valid in hole_counts):
        raise ValueError("Die Löcher der Vegetationsmaske konnten nicht gelesen werden.")
    if all(holes == 0 for holes, _ in hole_counts):
        return [_outer_ring(polygon, index, elevation) for index in range(count)]

    # A spline encodes one closed contour. Triangulate the occupied area and
    # union these contours again in PCG before creating the exclusion surface.
    mesh = unreal.DynamicMesh()
    options = unreal.GeometryScriptPolygonsTriangulationOptions(
        still_append_on_triangulation_error=False,
    )
    _, failed = unreal.GeometryScript_Primitives.append_polygon_list_triangulation(
        mesh, unreal.GeometryScriptPrimitiveOptions(), unreal.Transform(), polygon, options,
    )
    rings = []
    for index in range(mesh.get_triangle_count()):
        valid, *vertices = unreal.GeometryScript_MeshQueries.get_triangle_positions(mesh, index)
        if not valid:
            raise ValueError("Ein Maskendreieck konnte nicht gelesen werden.")
        rings.append([roads.vec_data(unreal.Vector(point.x, point.y, elevation)) for point in vertices])
    if failed or not rings:
        raise ValueError("Die Vegetationsmaske mit Löchern konnte nicht trianguliert werden.")
    return rings


def _desired(plan):
    elevation = roads.plan_elevation(plan)
    bindings = buildings.scene_bindings(plan)
    sources = [buildings.native_source_geometry(plan, binding)[0] for binding in bindings.values()]
    if len(set(sources)) != len(sources):
        raise ValueError("Mehrere Gebäude-Bindungen nutzen dieselbe native Quellform.")

    providers = buildings.reservations(plan, bindings)
    for road in roads.members(plan, "Road").values():
        width, path, _ = roads.road_path(road)
        providers.append(("road", roads.corridor(path, width), road))

    desired = {}
    for kind, polygon, actor in sorted(providers, key=lambda entry: (entry[0], roads.actor_id(entry[2]))):
        category = roads.metadata(actor).get(CLEARANCE, ALL) if kind == "reserved_area" else ALL
        if category not in _CATEGORY_TAGS:
            raise ValueError(f"'{actor.get_actor_label()}' braucht {CLEARANCE}=All oder Woody.")
        try:
            rings = _spline_rings(polygon, elevation)
        except ValueError as error:
            raise ValueError(f"'{actor.get_actor_label()}': {error}") from error
        for index, ring in enumerate(rings):
            key = f"{kind}:{roads.actor_id(actor)}:{index}"
            desired[key] = (category, ring)
    return desired


def _container(plan):
    roads.require_plan(plan)
    matches = [actor for actor in plan.get_attached_actors()
               if actor.get_attach_parent_actor() == plan
               and roads.metadata(actor).get(_OWNER) == roads.actor_id(actor)]
    if len(matches) > 1:
        raise ValueError("Der Plan enthält mehrere registrierte Vegetationsmasken-Actors.")
    return matches[0] if matches else None


def validate_sources(plan):
    """Validate every mask provider before a related editor action writes."""
    _desired(plan)


def _inputs(node, label):
    return [edge.get_input_node() for pin in node.get_editor_property("input_pins")
            if str(pin.get_editor_property("properties").label) == label
            for edge in pin.get_editor_property("edges")
            if edge.get_output_node() == node]


def _uses_mask(graph, container, category):
    if not graph:
        return False
    nodes = list(graph.get_editor_property("nodes"))
    readers = [node for node in nodes if isinstance(node.get_settings(), unreal.PCGGetSplineSettings)
               and str(node.get_settings().get_editor_property("component_selector").component_selection_tag)
               == _CATEGORY_TAGS[category]]
    if len(readers) != 1:
        return False
    reader = readers[0]
    settings = reader.get_settings()
    selector = settings.get_editor_property("actor_selector")
    components = settings.get_editor_property("component_selector")
    if (selector.actor_filter != unreal.PCGActorFilter.FROM_INPUT
            or selector.include_children
            or str(selector.actor_reference_selector.get_name()) != "MaskActor"
            or components.component_selection != unreal.PCGComponentSelection.BY_TAG
            or not settings.get_editor_property("always_requery_actors")):
        return False
    inputs = _inputs(reader, "In")
    if len(inputs) != 1:
        return False
    reference = inputs[0].get_settings()
    if not isinstance(reference, unreal.PCGCreateAttributeSetSettings):
        return False
    source = reference.get_editor_property("attribute_types")
    path = unreal.SoftObjectPath()
    path.import_text(container.get_path_name())
    if (source.type != unreal.PCGMetadataTypes.SOFT_OBJECT_PATH
            or source.soft_object_path_value.export_text() != path.export_text()
            or str(reference.get_editor_property("output_target").get_name()) != "MaskActor"):
        return False

    # A stand-alone reference or disconnected mask branch cannot drive vegetation output.
    upstream = {reader}
    for step in (unreal.PCGCreatePolygon2DSettings, unreal.PCGPolygon2DOperationSettings,
                 unreal.PCGCreateSurfaceFromPolygon2DSettings):
        upstream = {node for node in nodes if isinstance(node.get_settings(), step)
                    and (step != unreal.PCGPolygon2DOperationSettings
                         or node.get_settings().get_editor_property("operation") == unreal.PCGPolygonOperation.UNION)
                    and upstream.intersection(_inputs(node, "In"))}
    differences = {node for node in nodes if isinstance(node.get_settings(), unreal.PCGDifferenceSettings)
                   and node.get_settings().get_editor_property("mode") == unreal.PCGDifferenceMode.DISCRETE
                   and upstream.intersection(_inputs(node, "Differences"))}
    return any(isinstance(node.get_settings(), unreal.PCGStaticMeshSpawnerSettings)
               and differences.intersection(_inputs(node, "In")) for node in nodes)


def validate_consumers(plan, components):
    """Accept two explicit, locally generated PCG consumers of this plan's mask."""
    container = _container(plan)
    if not container:
        raise ValueError("Der Plan besitzt noch keinen Masken-Actor. Zuerst die Masken veröffentlichen.")
    if set(components) != set(_CATEGORY_TAGS):
        raise ValueError("Je eine PCG-Komponente für All und Woody registrieren.")
    for category, component in components.items():
        if not isinstance(component, unreal.PCGComponent) or not unreal.SystemLibrary.is_valid(component):
            raise ValueError(f"Für {category} fehlt eine gültige PCG-Komponente.")
        owner = component.get_owner()
        if (not owner or owner.get_outer() != plan.get_outer()
                or not component.get_editor_property("activated")
                or component.get_editor_property("is_component_local")
                or component.get_editor_property("is_component_partitioned")
                or component.get_editor_property("regenerate_in_editor")
                or component.get_editor_property("generation_trigger")
                != unreal.PCGComponentGenerationTrigger.GENERATE_ON_DEMAND
                or not _uses_mask(component.get_graph(), container, category)):
            raise ValueError(f"Die PCG-Komponente für {category} muss die Masken dieses Plans direkt und auf Abruf lesen.")
    if components[ALL] == components[WOODY]:
        raise ValueError("All und Woody benötigen jeweils eine eigene PCG-Komponente.")


def _owned_components(container):
    owned = {}
    for component in container.get_components_by_class(unreal.SplineComponent):
        data = roads.attributes(component.component_tags)
        if data.get(_COMPONENT) != component.get_name():
            continue
        key = data[_PROVIDER]
        if key in owned:
            raise ValueError("Doppelter Provider-Eintrag im Vegetationsmasken-Actor.")
        owned[key] = component
    return owned


def _tags(component, key, category):
    roles = [f"{_COMPONENT}={component.get_name()}", f"{_PROVIDER}={key}", _CATEGORY_TAGS[WOODY]]
    if category == ALL:
        roles.append(_CATEGORY_TAGS[ALL])
    return roles


def _add_spline(container):
    editor = roads.SUBOBJECTS
    root = editor.k2_gather_subobject_data_for_instance(container)[0]
    params = unreal.AddNewSubobjectParams(parent_handle=root, new_class=unreal.SplineComponent)
    handle, reason = editor.add_new_subobject(params)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    if not lib.is_handle_valid(handle):
        raise RuntimeError(str(reason))
    return lib.get_associated_object(lib.get_data(handle))


def refresh(plan):
    """Publish validated masks for this plan and return the stable native mask Actor."""
    desired = _desired(plan)
    container = _container(plan)
    created = container is None
    if created:
        container = roads.ACTORS.spawn_actor_from_class(unreal.Actor, plan.get_actor_location())
        if not container:
            raise RuntimeError("Der Vegetationsmasken-Actor konnte nicht angelegt werden.")
    staged = {}
    try:
        if created:
            if container.get_outer() != plan.get_outer():
                raise ValueError("Vor dem ersten Refresh muss das Level des Plans aktiv sein.")
            container.set_actor_label(f"{plan.get_actor_label()} · Vegetationsmasken")
            rule = unreal.AttachmentRule.KEEP_WORLD
            if not container.attach_to_actor(plan, "", rule, rule, rule, False):
                raise RuntimeError("Der Vegetationsmasken-Actor konnte nicht am Plan befestigt werden.")
            roads.set_metadata(container, **{_OWNER: roads.actor_id(container)})
        owned = _owned_components(container)
        pending = {
            key: (category, ring) for key, (category, ring) in desired.items()
            if key not in owned or list(map(str, owned[key].component_tags)) != _tags(owned[key], key, category)
            or not owned[key].is_closed_loop() or roads.points(owned[key]) != ring
        }
        for key, (_, ring) in pending.items():
            staged[key] = _add_spline(container)
            roads.set_points(staged[key], ring, True)
        for key, component in staged.items():
            component.set_editor_property("component_tags", _tags(component, key, pending[key][0]))
    except Exception:
        if created:
            roads.ACTORS.destroy_actor(container)
        else:
            for component in staged.values():
                component.destroy_component(container)
        raise
    for key, component in owned.items():
        if key in pending or key not in desired:
            component.destroy_component(container)
    return container


def add_mask_surface(graph, container, category, *, origin=(0, 0)):
    """Read the explicit native mask Actor returned by refresh(plan)."""
    tag = _CATEGORY_TAGS[category]
    if _container(container.get_attach_parent_actor()) != container:
        raise ValueError("Der Actor ist keine registrierte Vegetationsmaske.")
    reference, attribute = graph.add_node_of_type(unreal.PCGCreateAttributeSetSettings)
    source = attribute.get_editor_property("attribute_types")
    path = unreal.SoftObjectPath()
    path.import_text(container.get_path_name())
    source.set_editor_properties({
        "type": unreal.PCGMetadataTypes.SOFT_OBJECT_PATH,
        "soft_object_path_value": path,
    })
    output = attribute.get_editor_property("output_target")
    output.import_text("PCGBegin(MaskActor)PCGEnd")
    attribute.set_editor_properties({"attribute_types": source, "output_target": output})

    spline, settings = graph.add_node_of_type(unreal.PCGGetSplineSettings)
    selector = settings.get_editor_property("actor_selector")
    selector.set_editor_property("actor_filter", unreal.PCGActorFilter.FROM_INPUT)
    actor_reference = selector.get_editor_property("actor_reference_selector")
    actor_reference.import_text("PCGBegin(MaskActor)PCGEnd")
    selector.set_editor_property("actor_reference_selector", actor_reference)
    settings.set_editor_property("actor_selector", selector)
    selector = settings.get_editor_property("component_selector")
    selector.set_editor_property("component_selection", unreal.PCGComponentSelection.BY_TAG)
    selector.set_editor_property("component_selection_tag", tag)
    settings.set_editor_properties({
        "component_selector": selector, "always_requery_actors": True, "components_must_overlap_self": False,
    })
    polygon, _ = graph.add_node_of_type(unreal.PCGCreatePolygon2DSettings)
    union, settings = graph.add_node_of_type(unreal.PCGPolygon2DOperationSettings)
    settings.set_editor_properties({
        "operation": unreal.PCGPolygonOperation.UNION,
        "metadata_mode": unreal.PCGPolygonOperationMetadataMode.NONE,
    })
    surface, _ = graph.add_node_of_type(unreal.PCGCreateSurfaceFromPolygon2DSettings)
    nodes = (reference, spline, polygon, union, surface)
    titles = ("Masken-Actor des Plans", f"Maskensplines ({category})", "Flächenkonturen",
              "Belegte Fläche vereinen", "Vegetation ausschließen")
    for index, (node, title) in enumerate(zip(nodes, titles)):
        node.set_editor_property("node_title", title)
        node.set_node_position(origin[0] + 300 * index, origin[1])
    for source, target in zip(nodes, nodes[1:]):
        if not graph.add_edge(source, "Out", target, "In"):
            raise RuntimeError("Die native Vegetationsmasken-Kette konnte nicht verbunden werden.")
    return surface
