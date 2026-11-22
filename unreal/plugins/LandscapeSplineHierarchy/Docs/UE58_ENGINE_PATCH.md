# Minimal UE 5.8 Source Hooks

This patch is required only for hard group visibility/locking and exact global terrain priority. X-Ray and through-object native picking already work in an unmodified Launcher build through `SetDepthPriorityGroup(SDPG_Foreground)`.

The Launcher engine contains readable source for reference but cannot be rebuilt as a custom engine. Apply these changes to an Epic GitHub/source build of the matching UE 5.8 revision.

## 1. Add a public Landscape delegate header

Create `Engine/Source/Runtime/Landscape/Public/LandscapeSplineEditorExtension.h`:

```cpp
#pragma once

#include "CoreMinimal.h"

class ULandscapeSplinesComponent;

DECLARE_DELEGATE_RetVal_OneParam(bool, FLandscapeSplineIsElementVisible, const UObject*);
DECLARE_DELEGATE_RetVal_OneParam(bool, FLandscapeSplineIsElementLocked, const UObject*);
DECLARE_DELEGATE_RetVal_OneParam(int32, FLandscapeSplineGetElementPriority, const UObject*);

struct LANDSCAPE_API FLandscapeSplineEditorExtensionDelegates
{
    inline static FLandscapeSplineIsElementVisible IsElementVisible;
    inline static FLandscapeSplineIsElementLocked IsElementLocked;
    inline static FLandscapeSplineGetElementPriority GetElementPriority;
};
```

The plugin detects this header with `__has_include` and binds the visibility, lock and priority delegates during startup.

## 2. Native visibility

Modify `Runtime/Landscape/Private/LandscapeSplines.cpp`:

1. Include `LandscapeSplineEditorExtension.h`.
2. In the `FLandscapeSplinesSceneProxy` constructor, skip a control point or segment when `IsElementVisible` is bound and returns false.
Store the source component as `const ULandscapeSplinesComponent* ComponentOwner` on the proxy so the visibility delegate can identify group members. Do not change the depth-priority assignment: the plugin sets the component's public DPG directly and the existing proxy continues to submit its native hit proxies.

## 3. Hard lock in the native tool

Modify `Editor/LandscapeEditor/Private/LandscapeEdModeSplineTools.cpp` and include the new header.

Add:

```cpp
static bool IsExtensionLocked(const UObject* Object)
{
    return Object &&
        FLandscapeSplineEditorExtensionDelegates::IsElementLocked.IsBound() &&
        FLandscapeSplineEditorExtensionDelegates::IsElementLocked.Execute(Object);
}
```

Reject locked elements in these native paths:

- `HandleClick()` after resolving `ClickedControlPoint` / `ClickedSplineSegment`;
- tangent press before assigning `DraggingTangent_Segment`;
- Ctrl-click split/add operations;
- `BeginTransformInternal()` and `InputDelta()` if any selected element is locked;
- delete and duplicate commands before opening their transaction.

Returning `true` for the consumed click and refusing the transaction preserves selection while preventing mutation.

## 4. Exact group-priority raster order

Modify `Runtime/Landscape/Private/LandscapeSplineRaster.cpp`. The work list must be built in `ULandscapeInfo::ApplySplines()`, before the current `ForAllSplineActors()` boundary.

Do not combine items only inside `ApplySplinesInternal()`. That would interleave points and segments inside one component, but Unreal would still exhaust one spline actor/component before the next. A later Priority 50 actor could still overwrite an earlier Priority 100 actor.

```cpp
enum class ESplineRasterElement : uint8
{
    ControlPoint,
    Segment
};

struct FSplineRasterItem
{
    TScriptInterface<ILandscapeSplineInterface> Owner;
    ULandscapeSplinesComponent* Component = nullptr;
    const UObject* Element = nullptr;
    ESplineRasterElement Type = ESplineRasterElement::ControlPoint;
    int32 Priority = 0;
    int32 StableOrder = 0;
};

TArray<FSplineRasterItem> Items;
int32 StableOrder = 0;

ForAllSplineActors([&](TScriptInterface<ILandscapeSplineInterface> Owner)
{
    if (!Owner || !Owner->IsSplineOwnerValid()) return;
    ULandscapeSplinesComponent* Component = Owner->GetSplinesComponent();
    if (!Component || !Component->IsRegistered()) return;

    auto GetPriority = [](const UObject* Element)
    {
        return FLandscapeSplineEditorExtensionDelegates::GetElementPriority.IsBound()
            ? FLandscapeSplineEditorExtensionDelegates::GetElementPriority.Execute(Element)
            : 0;
    };

    for (const ULandscapeSplineControlPoint* Point : Component->ControlPoints)
    {
        Items.Add({ Owner, Component, Point, ESplineRasterElement::ControlPoint,
            GetPriority(Point), StableOrder++ });
    }
    for (const ULandscapeSplineSegment* Segment : Component->Segments)
    {
        Items.Add({ Owner, Component, Segment, ESplineRasterElement::Segment,
            GetPriority(Segment), StableOrder++ });
    }
});

Items.StableSort([](const FSplineRasterItem& A, const FSplineRasterItem& B)
{
    if (A.Priority != B.Priority) return A.Priority < B.Priority;
    return A.StableOrder < B.StableOrder;
});
```

The global `StableOrder` must follow Unreal's existing deterministic owner traversal and array order. When the delegate is unbound, all items have Priority 0 and native order is preserved.

Extract the existing control-point and segment loop bodies into element-level helpers. Each helper must receive the item's owner/component, the correct owner-specific `SplineToLandscape` transform, the shared edit-data interface and modified-component set, the Landscape bounds, and the existing modulation callback. Sort once and execute the complete list low-to-high. Do not leave the old per-owner `ApplySplinesInternal()` loop active or the spline data will be rasterized twice.

Retain the native component update, output-set, hash and edit-layer notification behavior. Do not change height flags/alpha, raise/lower behavior, falloff, weightmap modulation, layer clearing, or modified-component tracking.

This is the key detail: sorting `ControlPoints` and `Segments` separately, or combining them only per component, cannot guarantee priority across a control-point/segment overlap or separate Landscape Spline Actors. Only one global low-to-high list can.

Skip invisible elements before rasterization only if `IsElementVisible` is intended to affect terrain as well as editor display. The plugin's intended behavior is that `Visible` controls editor display only; therefore the raster loop should not use that delegate.

## Verification

After rebuilding the source engine:

1. The plugin panel must show `UE 5.8 engine hooks detected`.
2. Toggle X-Ray in the unpatched Launcher build with a spline behind a closed Static Mesh and verify both segment and control-point hit proxies.
3. Lock a group and test click, tangent drag, widget transform, duplicate, split, and delete.
4. Cross a Priority 50 road with Priority 100 road at different Z values and rebuild the spline layer; Priority 100 must own the final overlap.
5. Repeat with an overlap involving a control-point footprint, not only two segment middles.
6. Repeat with the two roads stored in different `ALandscapeSplineActor` instances.
