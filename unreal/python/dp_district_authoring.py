"""Independent editable districts and repeatable, manually overridable blockouts."""
import math
import unreal
import roads as r
import dp_buildings as b
from dp_district_layout import candidates, Preset

SLOT = 'DistrictLayoutSlot'
STAMP = 'DistrictLayoutTransform'


def preset_values(asset):
    if asset is None:
        raise ValueError('Ein Distriktstil fehlt.')
    try:
        lo = asset.get_editor_property('MinimumSizeCm')
        hi = asset.get_editor_property('MaximumSizeCm')
        return Preset(asset.get_editor_property('SpacingCm'), (lo.x,hi.x), (lo.y,hi.y), (lo.z,hi.z),
                      asset.get_editor_property('JitterCm'), asset.get_editor_property('RotationDegrees'))
    except Exception as error:
        raise ValueError('Die Auswahl ist kein gültiger Distriktstil.') from error


def validate_boundary(plan, district):
    r.require_member(plan, district, 'District')
    shape = r.actor_polygon(district)
    if r.area(shape) <= r.MARGIN_CM2:
        raise ValueError('Der Distrikt braucht eine geschlossene Fläche.')
    if r.area(r.POLYGONS.polygons_difference(shape, r.actor_polygon(plan))) > r.MARGIN_CM2:
        raise ValueError('Die Distriktgrenze liegt außerhalb des Planungsbereichs.')
    for other in r.members(plan, 'District').values():
        if other != district and r.area(r.POLYGONS.polygons_intersection(shape, r.actor_polygon(other))) > r.MARGIN_CM2:
            raise ValueError('Die Distriktgrenze überlappt einen anderen Distrikt.')
    return shape


def create_district(plan, blueprint_class, name, points):
    r.require_plan(plan)
    actor = b.ACTORS.spawn_actor_from_class(blueprint_class, unreal.Vector())
    try:
        actor.set_actor_label(name)
        components = actor.get_components_by_class(unreal.SplineComponent)
        if len(components) != 1:
            raise ValueError('Die Distriktvorlage braucht genau einen Außenspline.')
        r.set_points(components[0], points, True)
        r.attach_member(plan, actor, 'District')
        validate_boundary(plan, actor)
        return actor
    except Exception:
        b.ACTORS.destroy_actor(actor)
        raise


def candidate_polygon(row):
    x, y = row['center_cm']
    width, depth, _ = row['size_cm']
    angle = math.radians(row['yaw_degrees'])
    c, s = math.cos(angle), math.sin(angle)
    points = [unreal.Vector2D(x+u*c-v*s, y+u*s+v*c)
              for u,v in ((-width/2,-depth/2),(width/2,-depth/2),(width/2,depth/2),(-width/2,depth/2))]
    return r.POLYGONS.create_polygon_list_from_single_polygon(
        r.SIMPLE.conv_array_of_vector2d_to_geometry_script_simple_polygon(points), [])


def adopt_spline(plan, actor, role):
    """Explicitly register a user-placed spline actor, retaining its authored shape."""
    if role not in ('Road', 'District'):
        raise ValueError('Straße oder Distrikt erwartet.')
    if role == 'District':
        preset_values(actor.get_editor_property('LayoutPreset'))
        if list(actor.get_editor_property('LayoutBuildings')):
            raise ValueError('Kopierter Distrikt enthält Gebäudereferenzen; zuerst Zuordnung klären.')
    previous_tags = list(actor.get_editor_property('Tags'))
    r.attach_member(plan, actor, role)
    try:
        if role == 'Road':
            r.road_path(actor)
        else:
            validate_boundary(plan, actor)
    except Exception:
        rule = unreal.DetachmentRule.KEEP_WORLD
        actor.detach_from_actor(rule,rule,rule)
        actor.set_editor_property('Tags',previous_tags)
        raise
    return {'decision':'registered','role':role}


def remove_generated_pair(binding):
    source = binding.get_editor_property('NativeBlockoutSource')
    transform, label = source.get_actor_transform(), source.get_actor_label()
    tags, folder = list(source.get_editor_property('Tags')), source.get_folder_path()
    spatial = source.get_editor_property('is_spatially_loaded')
    if not b.ACTORS.destroy_actor(source):
        raise ValueError('Eine alte Blockform konnte nicht entfernt werden; sie bleibt registriert.')
    if not b.ACTORS.destroy_actor(binding):
        replacement = b.spawn_mesh(b.CUBE, r.vec_data(transform.translation), r.vec_data(transform.scale3d),
                                   label, b.SOURCE, rotation=transform.rotation.rotator())
        replacement.set_editor_property('Tags',tags)
        replacement.set_folder_path(folder)
        replacement.set_editor_property('is_spatially_loaded',spatial)
        binding.set_editor_property('NativeBlockoutSource',replacement)
        r.set_metadata(binding,**{STAMP:b.source_geometry_hash(replacement)})
        raise ValueError('Eine alte Gebäudezuordnung konnte nicht entfernt werden; ihre Blockform wurde wiederhergestellt.')


def regenerate(plan, district, theme):
    """Explicit rebuild; keep edited or detailed houses, never mutate other districts."""
    validate_boundary(plan, district)
    preset = preset_values(district.get_editor_property('LayoutPreset'))
    seed = district.get_editor_property('LayoutSeed')
    b.load_assembly(theme)  # Validate placeholder theme before creating any actors.
    _, samples = r.planar_path(district, r.loops(district)['outer'], True, r.plan_elevation(plan))
    box = (min(p[0] for p in samples), min(p[1] for p in samples),
           max(p[0] for p in samples), max(p[1] for p in samples))
    requested = candidates(box, preset, seed)
    all_bindings = b.scene_bindings(plan)
    current, protected = {}, []
    refs = list(district.get_editor_property('LayoutBuildings'))
    for binding in refs:
        if not unreal.SystemLibrary.is_valid(binding) or binding not in all_bindings.values() or binding.get_attach_parent_actor() != district:
            raise ValueError('Eine verwaltete Gebäudereferenz fehlt oder gehört zu einem anderen Distrikt.')
        source = binding.get_editor_property('NativeBlockoutSource')
        if (not unreal.SystemLibrary.is_valid(source) or not isinstance(source,unreal.StaticMeshActor)
                or source.static_mesh_component.static_mesh != b.CUBE or b.SOURCE not in b.tags(source)
                or r.metadata(source).get(r.PLAN_SCOPE) != r.require_plan(plan)):
            raise ValueError('Eine Distrikt-Quellform fehlt oder gehört zu einem anderen Plan.')
        data = r.metadata(binding)
        slot = data.get(SLOT)
        if not slot or slot in current:
            raise ValueError('Widersprüchliche Distrikt-Slotzuordnung.')
        current[slot] = binding
        if (data.get(STAMP) != b.source_geometry_hash(source) or b.owned_details(binding)
                or binding.get_editor_property('SlotModuleOverrides') or binding.get_editor_property('LockedSlotIds')):
            protected.append(binding)
    automatic = {key: value for key,value in current.items() if value not in protected}
    auto_sources = {value.get_editor_property('NativeBlockoutSource') for value in automatic.values()}
    binding_class = unreal.load_object(None,b.CLASS_PATH)
    all_sources = [actor.get_editor_property('NativeBlockoutSource') for actor in b.ACTORS.get_all_level_actors()
                   if actor.get_class()==binding_class and actor.get_editor_property('BindingId')==r.actor_id(actor)]
    if any(all_sources.count(source)!=1 for source in auto_sources):
        raise ValueError('Eine automatisch verwaltete Blockform wird von mehreren Gebäuden benutzt.')
    for binding in automatic.values():
        b.native_source_geometry(plan,binding)
    avoid = [entry for entry in b.reservations(plan, all_bindings) if entry[2] not in auto_sources]
    allowed = r.available_districts(plan)[r.metadata(district)[r.IDENTITY]]
    planned, rejected = [], 0
    protected_slots = {r.metadata(value)[SLOT] for value in protected}
    for row in requested:
        if row['slot_id'] in protected_slots:
            continue
        shape = candidate_polygon(row)
        if b.assess_footprint(shape, allowed, avoid)['decision'] != 'fits':
            rejected += 1
            continue
        planned.append(row)
        avoid.append(('new_layout', shape, row['slot_id']))
    # Stage replacements first. Existing output survives a staging failure.
    staged, kept = [], []
    try:
        for row in planned:
            old = automatic.get(row['slot_id'])
            expected = {'center': row['center_cm'], 'size': row['size_cm'], 'yaw': row['yaw_degrees']}
            recipe = r.digest(expected)
            if old is not None and r.metadata(old).get('DistrictLayoutRecipe') == recipe:
                kept.append(old)
                continue
            actor = b._new_building(plan, district, (*row['center_cm'], r.plan_elevation(plan)),
                                    row['size_cm'], theme, district.get_actor_label()+' · '+row['slot_id'])
            staged.append(actor)
            source = actor.get_editor_property('NativeBlockoutSource')
            source.set_actor_rotation(unreal.Rotator(yaw=row['yaw_degrees']), False)
            r.set_metadata(actor, **{SLOT: row['slot_id'], STAMP: b.source_geometry_hash(source),
                                    'DistrictLayoutRecipe': recipe})
    except Exception:
        for actor in staged:
            b.ACTORS.destroy_actor(actor.get_editor_property('NativeBlockoutSource'))
            b.ACTORS.destroy_actor(actor)
        raise
    retained = protected + kept + staged
    retiring = [actor for actor in automatic.values() if actor not in kept]
    if not staged and not retiring:
        return {'created':0,'unchanged':len(kept),'manual_preserved':len(protected),
                'removed':0,'rejected':rejected,'total':len(refs)}
    district.modify()
    removed = 0
    try:
        for actor in retiring:
            remove_generated_pair(actor)
            removed += 1
    except Exception:
        # Keep surviving old references; roll back staged alternatives, not manual houses.
        try:
            for actor in staged:
                if unreal.SystemLibrary.is_valid(actor):
                    remove_generated_pair(actor)
        finally:
            district.set_editor_property('LayoutBuildings',[
                actor for actor in refs+staged if unreal.SystemLibrary.is_valid(actor)])
        raise
    district.set_editor_property('LayoutBuildings', retained)
    return {'created': len(staged), 'unchanged': len(kept), 'manual_preserved': len(protected),
            'removed': removed, 'rejected': rejected, 'total': len(retained)}
