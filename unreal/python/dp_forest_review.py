"""Register the saved Bachbogen context whenever the Forest map is opened."""

import unreal

import dp_buildings as buildings
import dp_vegetation_space as vegetation
import dp_worldbuilding_menu as menu
import roads


MAP = "/Game/DP/Forrest"
WORLD = MAP + ".Forrest"
PLAN_GUID = "DP.ForestReviewPlanGuid"
THEME_BINDING_GUID = "DP.ForestReviewThemeBindingGuid"
CONSUMER_GUID = "DP.ForestReviewConsumerGuid"
CONSUMER_CATEGORY = "DP.ForestReviewConsumerCategory"
EDITOR = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
_hooked = False
_registered_plan = None


def single(matches, description):
    matches = list(matches)
    if len(matches) != 1:
        raise ValueError(f"Bachbogen: {description} ist nicht eindeutig vorhanden.")
    return matches[0]


def plans():
    return [actor for actor in roads.ACTORS.get_all_level_actors()
            if roads.metadata(actor).get(roads.ROLE) == "Plan"
            and roads.metadata(actor).get(PLAN_GUID) == roads.actor_id(actor)]


def start():
    global _registered_plan
    world = EDITOR.get_editor_world()
    if not world or world.get_path_name() != WORLD:
        raise ValueError(f"Bachbogen: zuerst {MAP} öffnen.")
    plan = single(plans(), "der Reviewplan")
    theme_binding = buildings.scene_bindings(plan).get(roads.metadata(plan).get(THEME_BINDING_GUID))
    if theme_binding is None:
        raise ValueError("Bachbogen: Das gespeicherte Mansion-Theme-Binding fehlt.")
    theme = theme_binding.get_editor_property("ThemeDefinition")

    owners = [actor for actor in plan.get_attached_actors() if actor.get_attach_parent_actor() == plan
              and roads.metadata(actor).get(CONSUMER_GUID) == roads.actor_id(actor)]
    components = {}
    for category in (vegetation.ALL, vegetation.WOODY):
        owner = single((actor for actor in owners if roads.metadata(actor).get(CONSUMER_CATEGORY) == category),
                       f"der PCG-Abnehmer {category}")
        components[category] = single(owner.get_components_by_class(unreal.PCGComponent), f"PCG-Komponente {category}")

    entries = menu.register_menu(plan, theme, vegetation_components=components)
    if _registered_plan != plan:
        unreal.log("DP Bachbogen bereit. Im Outliner 'Review Worldbuilding' öffnen.")
    _registered_plan = plan
    return plan, components, entries


def refresh(_filename=None, _as_template=False):
    global _registered_plan
    world = EDITOR.get_editor_world()
    try:
        if world and world.get_path_name() == WORLD and plans():
            start()
        elif _registered_plan is not None:
            if menu._context and menu._context[0] == _registered_plan:
                menu.unregister_menu()
            _registered_plan = None
    except ValueError as error:
        unreal.log_warning(str(error))


def install():
    global _hooked
    _, _, switches = unreal.SystemLibrary.parse_command_line(unreal.SystemLibrary.get_command_line())
    if any(key.casefold() == "run" for key in switches):
        return
    if not _hooked:
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        levels.on_map_opened.add_callable(refresh)
        _hooked = True
    refresh()


if __name__ == "__main__":
    start()
