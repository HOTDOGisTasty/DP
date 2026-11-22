"""Explicitly registered native Actor context actions for one plan and default theme."""

import unreal

import dp_buildings as buildings
import dp_vegetation_space as vegetation
import roads
from dp_fixed_assembly import load_assembly


PARENT = "LevelEditor.ActorContextMenu"
OWNER = "DPScopedWorldbuilding"
SUBMENU = PARENT + "." + OWNER
SECTION = "DPActions"
ACTIONS = {
    "AdoptDistrict": ("Spline als Distrikt aufnehmen", "Ordnet einen frei gezeichneten Distrikt dem aktiven Plan zu. Straßen sind nicht erforderlich."),
    "AdoptRoad": ("Spline als Straße aufnehmen", "Ordnet eine offene Straßenspline mit Breite in cm dem aktiven Plan zu."),
    "DistrictLayout": ("Distrikt-Blockformen neu verteilen", "Nutzt Stil und Seed eines Distrikts. Von Hand geänderte oder detaillierte Häuser bleiben erhalten."),
    "Blockouts": ("Blockformen", "Ergänzt passende Baukörper in ausgewählten angenommenen Distrikten."),
    "BlockoutsFromTheme": ("Blockformen mit gewählter Vorlage",
                           "Ein Building-Theme im Content Browser und Distrikte im Level wählen. Ergänzt neue Häuser in den Vorlagenmaßen; bestehende Häuser bleiben erhalten."),
    "Activate": ("Details aktivieren", "Aktiviert Details für ausgewählte Gebäude oder Distrikte."),
    "Update": ("Auswahl aktualisieren", "Aktualisiert bereits aktivierte Gebäude der Auswahl."),
    "Cleanup": ("Erzeugte Gebäudedetails bereinigen",
                "Entfernt nur registrierte Details ausgewählter Gebäude. Blockformen, Modulwahlen und manuelle Kopien bleiben erhalten. Details aktivieren baut sie erneut auf."),
    "StageModule": ("Modul aus Content Browser vormerken",
                    "Eine ModuleDefinition im Content Browser und Detailmodule im Level wählen. Speichert die Auswahl; danach Auswahl aktualisieren."),
    "ResetModule": ("Modulauswahl zurücksetzen",
                    "Entfernt eigene Modulwahlen nur für die gewählten Detailmodule. Danach Auswahl aktualisieren."),
}
_entries = {}
_context = None
_run = None
last_result = None


class _VegetationRun:
    def __init__(self, components, status):
        self.components = dict(components)
        self.status = status
        self.states = status["components"]
        self.observers = {}
        self.tick_handle = None
        native = unreal.DPVegetationObservationState
        self.labels = {
            native.WAITING: "not_started",
            native.GENERATING: "generating",
            native.COMPLETED: "completed",
            native.CANCELLED: "cancelled",
            native.COMPLETION_MISSING: "completion_missing",
        }

    def start(self):
        try:
            for category, component in self.components.items():
                observer = unreal.DPVegetationObserver.observe(component)
                if not observer:
                    raise RuntimeError(f"PCG-Abnehmer {category} konnte nicht beobachtet werden.")
                self.observers[category] = observer
            for category, component in self.components.items():
                component.generate_local(True)
        except Exception as error:
            self.status["error"] = str(error)
        for category in self.states:
            if category not in self.observers:
                self.states[category] = "not_started"
        self.check_pending()
        if _run is self:
            self.tick_handle = unreal.register_slate_post_tick_callback(self.check_pending)

    def check_pending(self, _delta=None):
        for category, observer in self.observers.items():
            self.states[category] = self.labels[observer.get_state()]
        self._finish_if_ready()

    def _finish_if_ready(self):
        global _run
        if _run is not self or "generating" in self.states.values():
            return
        if self.tick_handle is not None:
            unreal.unregister_slate_post_tick_callback(self.tick_handle)
            self.tick_handle = None
        for observer in self.observers.values():
            observer.stop()
        self.observers.clear()
        _run = None
        if set(self.states.values()) == {"completed"} and "error" not in self.status:
            self.status["status"] = "completed"
            unreal.log("DP Worldbuilding · Vegetation: beide PCG-Komponenten abgeschlossen.")
        else:
            self.status["status"] = "incomplete"
            unreal.log_warning(f"DP Worldbuilding · Gebäudeaktion ausgeführt. Vegetation unvollständig {self.status}.")


def _busy(component):
    return unreal.DPWorldbuildingEditorLibrary.is_component_busy(component)


def _require_vegetation_helper():
    names = ("DPWorldbuildingEditorLibrary", "DPVegetationObserver", "DPVegetationObservationState")
    if not all(hasattr(unreal, name) for name in names):
        raise ValueError("Für die Vegetationsbedienung muss das aktuelle DP-Editor-Hilfsmodul geladen sein.")


def _require_idle():
    if _run is not None:
        _run.check_pending()
    if _run is not None:
        raise ValueError("Die laufende Vegetationsaktualisierung muss zuerst abschließen.")


def dispatch(action, plan, theme, selected_actors, *, vegetation_components=None, selected_module=None, selected_theme=None):
    global _run
    scope = roads.require_plan(plan)
    if plan not in buildings.ACTORS.get_all_level_actors():
        raise ValueError("Der registrierte Planungsbereich gehört nicht zum geladenen Level.")
    selected = list(selected_actors)
    if not selected:
        raise ValueError("Bitte Gebäude oder angenommene Distrikte dieses Plans auswählen.")
    if action in ("AdoptDistrict", "AdoptRoad"):
        _require_idle()
        if len(selected) != 1:
            raise ValueError("Genau einen neuen Spline-Actor auswählen.")
        import dp_district_authoring as district_authoring
        role = "District" if action == "AdoptDistrict" else "Road"
        result = district_authoring.adopt_spline(plan, selected[0], role)
        return {"action": action, "targets": {roads.actor_id(selected[0]): result}}
    if action == "BlockoutsFromTheme":
        if selected_theme is None:
            raise ValueError("Genau ein Building-Theme im Content Browser auswählen.")
        try:
            load_assembly(selected_theme)
        except Exception as error:
            raise ValueError("Die Auswahl ist keine gültige Gebäudevorlage: " + str(error)) from error
        theme = selected_theme
    if action in ("StageModule", "ResetModule"):
        _require_idle()
        if action == "StageModule" and selected_module is None:
            raise ValueError("Genau eine ModuleDefinition im Content Browser auswählen.")
        result = buildings.stage_slot_selection(
            plan, selected, selected_module if action == "StageModule" else None)
        return {"action": action, "plan_id": scope, "building_ids": sorted(result),
                "district_ids": [], "targets": result}
    areas = {actor: key for key, actor in roads.members(plan, "District").items()}
    bindings = buildings.scene_bindings(plan)
    building_ids, district_ids = set(), set()
    for actor in selected:
        if actor in areas:
            district_ids.add(areas[actor])
            continue
        if action in ("Blockouts", "BlockoutsFromTheme", "DistrictLayout"):
            raise ValueError("Für Blockformen ausschließlich angenommene Distrikte dieses Plans auswählen.")
        hits = [
            key for key, binding in bindings.items()
            if actor == binding or actor == binding.get_editor_property("NativeBlockoutSource")
            or actor in list(binding.get_editor_property("PublishedDetailActors"))
        ]
        if len(hits) != 1:
            raise ValueError(f"„{actor.get_actor_label()}“ gehört zu keiner eindeutigen Gebäudeauswahl dieses Plans.")
        building_ids.add(hits[0])
    selected_ids = {"building_ids": sorted(building_ids), "district_ids": sorted(district_ids)}
    _require_idle()
    if vegetation_components:
        _require_vegetation_helper()
        vegetation.validate_consumers(plan, vegetation_components)
        if any(_busy(component) for component in vegetation_components.values()):
            raise ValueError("Eine registrierte PCG-Komponente ist gerade beschäftigt.")
        vegetation.validate_sources(plan)
    if action in ("Blockouts", "BlockoutsFromTheme"):
        result = buildings.generate_blockouts(plan, theme, district_ids=selected_ids["district_ids"])
    elif action == "DistrictLayout":
        if len(district_ids) != 1:
            raise ValueError("Genau einen Distrikt zur Neuverteilung auswählen.")
        import dp_district_authoring as district_authoring
        district_id = next(iter(district_ids))
        district = next(actor for actor,key in areas.items() if key == district_id)
        result = {district_id: district_authoring.regenerate(plan, district, theme)}
    elif action == "Activate":
        result = buildings.activate_details(plan, **selected_ids)
    elif action == "Update":
        result = buildings.update_selection(plan, **selected_ids)
    elif action == "Cleanup":
        result = buildings.cleanup_details(plan, **selected_ids)
    else:
        raise ValueError("Unbekannte Worldbuilding-Aktion.")
    response = {"action": action, "plan_id": scope, **selected_ids, "targets": result}
    if vegetation_components:
        status = {"status": "generating", "components": dict.fromkeys(vegetation_components, "waiting")}
        response["vegetation"] = status
        try:
            vegetation.refresh(plan)
        except Exception as error:
            status.update(status="refresh_failed", error=str(error), components=dict.fromkeys(vegetation_components, "not_started"))
            unreal.log_warning(f"DP Worldbuilding · Gebäudeaktion ausgeführt. Vegetationsmasken nicht aktualisiert: {error}")
        else:
            _run = _VegetationRun(vegetation_components, status)
            _run.start()
            if status["status"] == "generating":
                unreal.log("DP Worldbuilding · Vegetationsaktualisierung läuft.")
    return response


@unreal.uclass()
class DPScopedWorldbuildingMenuEntry(unreal.ToolMenuEntryScript):
    @unreal.ufunction(override=True)
    def execute(self, context):
        global last_result
        name = str(self.get_editor_property("Data").name)
        label = ACTIONS[name][0]
        try:
            if _context is None:
                raise ValueError("Ein Planungsbereich und ein Theme müssen registriert sein.")
            plan, theme, components = _context
            selected_module = None
            selected_theme = None
            if name in ("StageModule", "BlockoutsFromTheme"):
                selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()
                if len(selected_assets) != 1:
                    kind = "ModuleDefinition" if name == "StageModule" else "Gebäudevorlage"
                    raise ValueError(f"Genau eine {kind} im Content Browser auswählen.")
                if name == "StageModule":
                    selected_module = selected_assets[0]
                else:
                    selected_theme = selected_assets[0]
            last_result = dispatch(name, plan, theme, buildings.ACTORS.get_selected_level_actors(),
                                   vegetation_components=components, selected_module=selected_module,
                                   selected_theme=selected_theme)
        except ValueError as error:
            last_result = {"action": name, "rejected": str(error)}
            unreal.log_warning(f"DP Worldbuilding · {label}: {error}")
            return
        if name in ("AdoptDistrict", "AdoptRoad"):
            unreal.log("DP Worldbuilding · Spline aufgenommen. Für neue Blockformen Distrikt-Blockformen neu verteilen wählen.")
        elif name == "DistrictLayout":
            result = next(iter(last_result["targets"].values()))
            unreal.log(f"DP Worldbuilding · {result['created']} neu, {result['unchanged']} unverändert, "
                       f"{result['manual_preserved']} manuell/detailliert erhalten.")
        elif name in ("StageModule", "ResetModule"):
            unreal.log("DP Worldbuilding · Modulauswahl gespeichert. Für die sichtbare Änderung Auswahl aktualisieren.")
        elif name in ("Blockouts", "BlockoutsFromTheme"):
            created = sum(len(result["created"]) for result in last_result["targets"].values())
            open_sites = sum(result["unfilled"] for result in last_result["targets"].values())
            unreal.log(f"DP Worldbuilding · {label}: {created} ergänzt, {open_sites} offene Plätze.")
        else:
            reasons = {
                "published": "erzeugt", "unchanged": "unverändert", "inactive": "inaktiv",
                "cleaned": "erzeugte Details entfernt, Blockform erhalten",
                "deactivated": "Blockform sichtbar, Details deaktiviert",
                "kit_does_not_fit": "Kit passt nicht zur Quellgröße",
                "outside_district_or_road_hole": "Grundriss außerhalb der Baufläche",
                "reserved_area": "Grundriss in Freihaltefläche", "manual_footprint": "manuelles Objekt im Grundriss",
                "existing_source": "Grundriss bereits belegt", "source_rebuild_disabled": "Quellaktualisierung aus",
                "existing_output": "vorige Gebäudeausgabe belegt diese Fläche noch",
            }
            notices = [reasons[result["decision"]] for result in last_result["targets"].values()]
            unreal.log(f"DP Worldbuilding · {label}: {', '.join(notices) or 'keine Gebäude'}")


def register_menu(plan, theme, *, vegetation_components=None):
    global _context
    roads.require_plan(plan)
    load_assembly(theme)
    components = dict(vegetation_components) if vegetation_components is not None else {}
    if vegetation_components is not None:
        _require_vegetation_helper()
        vegetation.validate_consumers(plan, components)
    if _entries and _context == (plan, theme, components):
        return dict(_entries)
    unregister_menu()
    _context = (plan, theme, components)
    menus = unreal.ToolMenus.get()
    parent = menus.extend_menu(PARENT)
    parent.add_sub_menu(OWNER, OWNER, OWNER, "DP Worldbuilding", "Aktionen im registrierten Planungsbereich.")
    for name, (label, tip) in ACTIONS.items():
        item = DPScopedWorldbuildingMenuEntry()
        item.init_entry(OWNER, SUBMENU, SECTION, name, label, tip)
        item.register_menu_entry()
        _entries[name] = item
    return dict(_entries)


def unregister_menu():
    global _context
    _require_idle()
    for item in _entries.values():
        item.unregister_menu_entry()
    unreal.ToolMenus.get().unregister_owner_by_name(OWNER)
    _entries.clear()
    _context = None
