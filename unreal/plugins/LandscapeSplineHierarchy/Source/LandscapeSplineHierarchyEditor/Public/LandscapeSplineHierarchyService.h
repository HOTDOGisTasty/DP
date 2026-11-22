#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"

class ALandscape;
class ALandscapeSplineHierarchyMetadata;
class ULandscapeSplineControlPoint;
class ULandscapeSplineSegment;
class ULandscapeSplinesComponent;
class UPackage;
class UWorld;
class FObjectPreSaveContext;

class LANDSCAPESPLINEHIERARCHYEDITOR_API FLandscapeSplineHierarchyService
{
public:
    static FLandscapeSplineHierarchyService& Get();

    void Startup();
    void Shutdown();

    bool IsAlwaysVisibleEnabled() const;
    void SetAlwaysVisibleEnabled(bool bEnabled);
    bool AreEngineHooksAvailable() const;

    ALandscapeSplineHierarchyMetadata* FindMetadata(ALandscape* Landscape) const;
    ALandscapeSplineHierarchyMetadata* FindOrCreateMetadata(ALandscape* Landscape);
    ALandscape* FindLandscapeFor(const UObject* SplineObject) const;
    ALandscape* FindCurrentLandscape() const;

    void GetSelectedSplineObjects(TArray<ULandscapeSplineControlPoint*>& OutControlPoints, TArray<ULandscapeSplineSegment*>& OutSegments) const;
    bool SelectSplineElementThroughGeometry(bool bAddToSelection, float ControlPointRadius = 24.0f, float SegmentRadius = 14.0f);
    void CreateGroupFromSelection(FName SuggestedName = NAME_None);
    ALandscapeSplineHierarchyMetadata* SynchronizeAutomaticSplineGraphs(ALandscape* Landscape);
    void RemoveGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId);
    void SelectGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId);
    void MoveGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId, int32 Direction);
    void SortGroups(ALandscapeSplineHierarchyMetadata* Metadata);
    void NotifyHierarchyChanged(ALandscapeSplineHierarchyMetadata* Metadata);

    const struct FLandscapeSplineGroup* FindGroupFor(const UObject* Object) const;

private:
    void ApplyAlwaysVisibleToSplineComponents();
    void RestoreSplineComponentDepthPriorityGroups();
    void HandlePreSavePackage(UPackage* Package, FObjectPreSaveContext SaveContext);
    bool TickAlwaysVisible(float DeltaTime);

    bool bAlwaysVisible = false;
    TMap<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8> OriginalDepthPriorityGroups;
    FTSTicker::FDelegateHandle AlwaysVisibleTickerHandle;
    FDelegateHandle PreSavePackageHandle;
};
