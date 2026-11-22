# UE 5.8 Native Landscape Spline Analysis

The analysis was performed against the UE 5.8 installation source at `Engine/Source`.

## Native data model

- `ULandscapeSplinesComponent` owns mutable arrays named `ControlPoints` and `Segments` and exposes them through `GetControlPoints()` and `GetSegments()`.
- `ULandscapeSplineControlPoint` stores graph adjacency in `ConnectedSegments`.
- `ULandscapeSplineSegment` stores its two endpoint connections in `Connections[2]`.
- There is no native road/spline-object boundary. A logical road must therefore be plugin metadata over graph elements.

## Rendering and hit proxies

Native editor rendering is implemented by the private `FLandscapeSplinesSceneProxy` in:

`Engine/Source/Runtime/Landscape/Private/LandscapeSplines.cpp`

Relevant UE 5.8 implementation:

- scene proxy starts near line 139;
- `CreateHitProxies()` creates `HLandscapeSplineProxy_Segment` and `HLandscapeSplineProxy_ControlPoint` near lines 220–233;
- `GetDynamicMeshElements()` selects `GetDepthPriorityGroup(View)` near line 253;
- lines and sprites use that depth priority near lines 281–345.

`ULandscapeSplinesComponent` inherits the public `UPrimitiveComponent::SetDepthPriorityGroup()` API. Setting it to `SDPG_Foreground` moves the existing native scene proxy, including its existing hit proxies, to foreground rendering. X-Ray and through-object native picking are therefore possible in a Launcher-engine plugin without drawing a second overlay. The plugin caches/restores the original value and restores it before package saves because `DepthPriorityGroup` is serialized.

## Native selection/tooling

`FLandscapeToolSplines` is private in:

`Engine/Source/Editor/LandscapeEditor/Private/LandscapeEdModeSplineTools.cpp`

`ULandscapeSplineSelection` is also declared in a private `LandscapeEditor` header and its selection methods are not exported as a stable public API. The plugin uses reflected transient selection arrays for `Select Group`, while the exact hard-lock hook must be checked inside the native tool before click, tangent drag, widget transform, split, delete, and duplication operations.

## Spline edit-layer update

The update path is:

1. `ALandscape::RequestSplineLayerUpdate()`
2. `ALandscape::UpdateAllLandscapeSplines()` in `LandscapeEditLayers.cpp` near line 8679
3. clear the reserved spline edit layer near line 8722
4. `ULandscapeInfo::ApplySplines()` near line 8727
5. `ULandscapeInfo::ApplySplinesInternal()` in `LandscapeSplineRaster.cpp` near line 662

Stock `ApplySplinesInternal()` rasterizes:

1. every control point in `SplineComponent->ControlPoints` (near line 685), then
2. every segment in `SplineComponent->Segments` (near line 756).

When editing the reserved spline layer, `FLandscapeSplineHeightsRasterPolicy::ProcessPixel()` alpha-blends the new height into the destination. Consequently later raster operations win in overlap areas. Reordering the public arrays gives deterministic low-to-high ordering within one native pass and one `ULandscapeSplinesComponent`. `ULandscapeInfo::ApplySplines()` also visits separate spline actors/components in an outer actor-path order. No public API can replace these nested passes with one global group-priority work list.

## API conclusion

An editor module using private `LandscapeEditor` headers is insufficient and brittle:

- private types are not a supported include surface;
- important selection methods are not exported;
- the native scene proxy lives in the Runtime Landscape module;
- raster order lives in Runtime Landscape private implementation.

The smallest exact solution for the remaining features is a source engine with a small public delegate header plus checks in the native spline tool and a globally ordered raster work list. The renderer needs a hook only for true per-group hiding, not for X-Ray.
