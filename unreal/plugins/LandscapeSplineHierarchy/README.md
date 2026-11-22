# Landscape Spline Hierarchy (UE 5.8)

Editor-only tools for native Landscape Splines created in **Landscape Mode → Manage → Splines**.

This plugin does not use Landmass, Blueprint Brushes, Water splines, or `USplineComponent` actors.

## Features

- Map-persistent logical groups containing native `ULandscapeSplineControlPoint` and `ULandscapeSplineSegment` objects.
- Name, numeric priority, visibility, lock state, group selection, move up/down, drag-and-drop, and non-destructive group removal.
- `Create Group From Selected Spline` uses the native selection and automatically includes selected segments' endpoints plus segments between selected control points.
- Stock-engine fallback sorts grouped native segments from low to high priority before requesting a spline-layer rebuild.
- Global `Always Visible Splines` draws the native spline scene proxy and its native hit proxies in the foreground.
- Per-group member and native-component counts expose unsupported priority cases.
- Visible capability warning when the optional engine hooks are absent.

## Open the UI

- **Tools → Landscape Splines → Landscape Spline Hierarchy**.

Keep **Landscape Mode → Manage → Splines** active while editing. The plugin deliberately leaves Unreal's native Landscape Spline Details customization intact.

Group metadata is stored in an editor-only `ALandscapeSplineHierarchyMetadata` actor in the Landscape's map. Removing a group never removes its native spline elements.

## Exact versus stock-engine behavior

The plugin builds and loads against an unmodified Launcher build of UE 5.8. In that configuration:

- grouping, rename, selection, drag/drop and ordering work;
- X-Ray rendering and through-object picking work through the public native `DepthPriorityGroup` API, without replacing the Landscape spline renderer or its hit proxies;
- overlapping grouped **segments inside one `ULandscapeSplinesComponent`** are reordered low-to-high through its public mutable array;
- terrain priority is best-effort only because stock UE has separate actor/component and control-point/segment passes;
- the reserved Splines edit layer must exist; otherwise Unreal's `RequestSplineLayerUpdate()` performs no rebuild;
- `Visible` and `Locked` remain metadata-only without engine hooks.

For hard group visibility/locking and exact global crossing priority, build UE 5.8 from source with the hooks described in [Docs/UE58_ENGINE_PATCH.md](Docs/UE58_ENGINE_PATCH.md).

## Build

```powershell
& 'C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat' `
  BuildPlugin `
  -Plugin='X:\Project\Plugins\LandscapeSplineHierarchy\LandscapeSplineHierarchy.uplugin' `
  -Package='X:\Build\LandscapeSplineHierarchy' `
  -TargetPlatforms=Win64 `
  -Rocket
```
