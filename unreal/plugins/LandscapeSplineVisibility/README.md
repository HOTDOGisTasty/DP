# Landscape Spline Visibility 1.2.3

Minimal Unreal Engine 5.8 editor plugin for native Landscape Splines under
`Landscape Mode -> Manage -> Splines`.

## What it does

- Renders native Landscape spline lines and control-point visualization in the editor foreground.
- Renders the spline and control points of Landmass brush actors in the editor foreground.
- Lets a visible Landmass control point be selected directly, even when a Landscape Streaming Proxy is behind it.
- Keeps Unreal's native hit proxies and native Landscape spline editing workflow.
- Restores the original depth-priority value before packages are saved.
- Adds `Tools -> Landscape Splines -> Always Visible Splines`.

The Landmass overlay remains a lightweight debug-canvas drawing. A small
editor-only input bridge performs a screen-space hit test on its visible control
points, then forwards the click to Unreal's native `USplineComponent`
visualizer. Point manipulation, multi-selection, tangent editing and Alt-drag
extrusion therefore remain native Unreal behavior.

The Landmass overlay uses Unreal's debug-canvas drawing service and does not
activate an editor mode. Landscape sculpt/paint brush cursors therefore remain
owned exclusively by the native Landscape tool.

The overlay is registered on Unreal's editor `ModeWidgets` viewport pass rather
than the selection-dependent Landmass spline visualization. It therefore stays
visible after the Landmass actor is deselected. Hiding the owner actor in the
Outliner still hides its overlay.

## What it deliberately does not do

- No hierarchy, groups, priority, outliner, metadata actors, or Details customization.
- No replacement spline editor or persistent helper actors/components.
- No access to private `ULandscapeSplineSelection` arrays.
- No runtime module or packaged-game cost.

The visibility toggle does not make Landscape Splines editable outside
`Landscape Mode -> Manage -> Splines`.
