#include "LandscapeSplineHierarchyService.h"

#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeSplineControlPoint.h"
#include "LandscapeSplineSegment.h"
#include "LandscapeSplinesComponent.h"
#include "ILandscapeSplineInterface.h"
#include "LandscapeSplineHierarchyTypes.h"

#include "Editor.h"
#include "EditorViewportClient.h"
#include "SceneView.h"
#include "Containers/Ticker.h"
#include "Engine/EngineTypes.h"
#include "Engine/Selection.h"
#include "EngineUtils.h"
#include "Misc/ConfigCacheIni.h"
#include "Modules/ModuleManager.h"
#include "PropertyEditorModule.h"
#include "ScopedTransaction.h"
#include "UObject/ObjectSaveContext.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"
#include "UObject/UnrealType.h"

#if __has_include("LandscapeSplineEditorExtension.h")
#include "LandscapeSplineEditorExtension.h"
#define LSH_WITH_ENGINE_HOOKS 1
#else
#define LSH_WITH_ENGINE_HOOKS 0
#endif

namespace
{
const TCHAR* SettingsSection = TEXT("/Script/LandscapeSplineHierarchyEditor.Settings");

UObject* FindNativeSplineSelection()
{
    UClass* SelectionClass = FindObject<UClass>(nullptr, TEXT("/Script/LandscapeEditor.LandscapeSplineSelection"));
    if (!SelectionClass)
    {
        return nullptr;
    }

    UObject* NewestSelection = nullptr;
    uint32 NewestUniqueId = 0;
    for (TObjectIterator<UObject> It; It; ++It)
    {
        if (It->IsA(SelectionClass) && It->GetOuter() == GetTransientPackage() && !It->HasAnyFlags(RF_BeginDestroyed | RF_FinishDestroyed))
        {
            if (!NewestSelection || It->GetUniqueID() > NewestUniqueId)
            {
                NewestSelection = *It;
                NewestUniqueId = It->GetUniqueID();
            }
        }
    }
    return NewestSelection;
}

void ReplaceObjectArrayProperty(UObject* Owner, const FName PropertyName, const TArray<UObject*>& Values)
{
    if (!Owner)
    {
        return;
    }

    FArrayProperty* ArrayProperty = FindFProperty<FArrayProperty>(Owner->GetClass(), PropertyName);
    FObjectPropertyBase* InnerObjectProperty = ArrayProperty ? CastField<FObjectPropertyBase>(ArrayProperty->Inner) : nullptr;
    if (!ArrayProperty || !InnerObjectProperty)
    {
        return;
    }

    void* ArrayAddress = ArrayProperty->ContainerPtrToValuePtr<void>(Owner);
    FScriptArrayHelper Helper(ArrayProperty, ArrayAddress);
    Helper.EmptyValues();
    for (UObject* Value : Values)
    {
        const int32 Index = Helper.AddValue();
        InnerObjectProperty->SetObjectPropertyValue(Helper.GetRawPtr(Index), Value);
    }
}

void ExpandSplineSelectionToConnectedMembers(
    const ALandscape* Landscape,
    TArray<ULandscapeSplineControlPoint*>& ControlPoints,
    TArray<ULandscapeSplineSegment*>& Segments)
{
    if (!Landscape)
    {
        return;
    }

    ControlPoints.RemoveAll([Landscape](const ULandscapeSplineControlPoint* Point)
    {
        return !IsValid(Point) || FLandscapeSplineHierarchyService::Get().FindLandscapeFor(Point) != Landscape;
    });
    Segments.RemoveAll([Landscape](const ULandscapeSplineSegment* Segment)
    {
        return !IsValid(Segment) || FLandscapeSplineHierarchyService::Get().FindLandscapeFor(Segment) != Landscape;
    });

    // A native Landscape spline is a graph, not a single UObject. Include the
    // endpoints of selected segments and the segments between selected points so
    // "Select all connected" produces a useful logical road group.
    for (ULandscapeSplineSegment* Segment : Segments)
    {
        for (const FLandscapeSplineSegmentConnection& Connection : Segment->Connections)
        {
            ULandscapeSplineControlPoint* Point = Connection.ControlPoint.Get();
            if (IsValid(Point))
            {
                ControlPoints.AddUnique(Point);
            }
        }
    }

    TSet<ULandscapeSplineControlPoint*> SelectedPoints;
    for (ULandscapeSplineControlPoint* Point : ControlPoints)
    {
        SelectedPoints.Add(Point);
    }
    for (TObjectIterator<ULandscapeSplineSegment> It; It; ++It)
    {
        ULandscapeSplineSegment* Segment = *It;
        if (Segment->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject)
            || FLandscapeSplineHierarchyService::Get().FindLandscapeFor(Segment) != Landscape)
        {
            continue;
        }

        ULandscapeSplineControlPoint* Start = Segment->Connections[0].ControlPoint.Get();
        ULandscapeSplineControlPoint* End = Segment->Connections[1].ControlPoint.Get();
        if (SelectedPoints.Contains(Start) && SelectedPoints.Contains(End))
        {
            Segments.AddUnique(Segment);
        }
    }
}
}

FLandscapeSplineHierarchyService& FLandscapeSplineHierarchyService::Get()
{
    static FLandscapeSplineHierarchyService Instance;
    return Instance;
}

void FLandscapeSplineHierarchyService::Startup()
{
    GConfig->GetBool(SettingsSection, TEXT("AlwaysVisibleSplines"), bAlwaysVisible, GEditorPerProjectIni);

    PreSavePackageHandle = UPackage::PreSavePackageWithContextEvent.AddRaw(
        this, &FLandscapeSplineHierarchyService::HandlePreSavePackage);
    AlwaysVisibleTickerHandle = FTSTicker::GetCoreTicker().AddTicker(
        FTickerDelegate::CreateRaw(this, &FLandscapeSplineHierarchyService::TickAlwaysVisible), 0.5f);

    if (bAlwaysVisible)
    {
        ApplyAlwaysVisibleToSplineComponents();
    }

#if LSH_WITH_ENGINE_HOOKS
    FLandscapeSplineEditorExtensionDelegates::IsElementVisible.BindLambda([this](const UObject* Object)
    {
        const FLandscapeSplineGroup* Group = FindGroupFor(Object);
        return !Group || Group->bVisible;
    });
    FLandscapeSplineEditorExtensionDelegates::IsElementLocked.BindLambda([this](const UObject* Object)
    {
        const FLandscapeSplineGroup* Group = FindGroupFor(Object);
        return Group && Group->bLocked;
    });
    FLandscapeSplineEditorExtensionDelegates::GetElementPriority.BindLambda([this](const UObject* Object)
    {
        const FLandscapeSplineGroup* Group = FindGroupFor(Object);
        return Group ? Group->Priority : 0;
    });
#endif
}

void FLandscapeSplineHierarchyService::Shutdown()
{
    if (AlwaysVisibleTickerHandle.IsValid())
    {
        FTSTicker::RemoveTicker(AlwaysVisibleTickerHandle);
        AlwaysVisibleTickerHandle.Reset();
    }
    if (PreSavePackageHandle.IsValid())
    {
        UPackage::PreSavePackageWithContextEvent.Remove(PreSavePackageHandle);
        PreSavePackageHandle.Reset();
    }
    RestoreSplineComponentDepthPriorityGroups();

#if LSH_WITH_ENGINE_HOOKS
    FLandscapeSplineEditorExtensionDelegates::IsElementVisible.Unbind();
    FLandscapeSplineEditorExtensionDelegates::IsElementLocked.Unbind();
    FLandscapeSplineEditorExtensionDelegates::GetElementPriority.Unbind();
#endif
}

bool FLandscapeSplineHierarchyService::IsAlwaysVisibleEnabled() const
{
    return bAlwaysVisible;
}

void FLandscapeSplineHierarchyService::SetAlwaysVisibleEnabled(bool bEnabled)
{
    if (bAlwaysVisible == bEnabled)
    {
        return;
    }

    bAlwaysVisible = bEnabled;
    GConfig->SetBool(SettingsSection, TEXT("AlwaysVisibleSplines"), bAlwaysVisible, GEditorPerProjectIni);
    GConfig->Flush(false, GEditorPerProjectIni);

    if (bAlwaysVisible)
    {
        ApplyAlwaysVisibleToSplineComponents();
    }
    else
    {
        RestoreSplineComponentDepthPriorityGroups();
    }

    if (GEditor)
    {
        GEditor->RedrawAllViewports(true);
    }
}

void FLandscapeSplineHierarchyService::ApplyAlwaysVisibleToSplineComponents()
{
    for (auto It = OriginalDepthPriorityGroups.CreateIterator(); It; ++It)
    {
        if (!It.Key().IsValid())
        {
            It.RemoveCurrent();
        }
    }

    for (TObjectIterator<ULandscapeSplinesComponent> It; It; ++It)
    {
        ULandscapeSplinesComponent* Component = *It;
        UWorld* World = Component ? Component->GetWorld() : nullptr;
        if (!IsValid(Component)
            || Component->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject)
            || !World
            || World->WorldType != EWorldType::Editor)
        {
            continue;
        }

        const TWeakObjectPtr<ULandscapeSplinesComponent> ComponentKey(Component);
        if (!OriginalDepthPriorityGroups.Contains(ComponentKey))
        {
            OriginalDepthPriorityGroups.Add(ComponentKey, static_cast<uint8>(Component->GetStaticDepthPriorityGroup()));
        }
        if (Component->GetStaticDepthPriorityGroup() != SDPG_Foreground)
        {
            // The stock Landscape spline scene proxy keeps its native hit proxies
            // while foreground DPG bypasses normal scene occlusion.
            Component->SetDepthPriorityGroup(SDPG_Foreground);
        }
    }
}

void FLandscapeSplineHierarchyService::RestoreSplineComponentDepthPriorityGroups()
{
    for (const TPair<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8>& Pair : OriginalDepthPriorityGroups)
    {
        if (ULandscapeSplinesComponent* Component = Pair.Key.Get())
        {
            Component->SetDepthPriorityGroup(static_cast<ESceneDepthPriorityGroup>(Pair.Value));
        }
    }
    OriginalDepthPriorityGroups.Reset();
}

void FLandscapeSplineHierarchyService::HandlePreSavePackage(UPackage* Package, FObjectPreSaveContext)
{
    if (!bAlwaysVisible || !Package)
    {
        return;
    }

    // DepthPriorityGroup is serialized by UPrimitiveComponent. Restore the real
    // value before the package is harvested; the editor ticker reapplies X-Ray on
    // the next frame without dirtying the level or leaking this editor preference.
    for (const TPair<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8>& Pair : OriginalDepthPriorityGroups)
    {
        ULandscapeSplinesComponent* Component = Pair.Key.Get();
        if (Component && Component->GetOutermost() == Package)
        {
            Component->SetDepthPriorityGroup(static_cast<ESceneDepthPriorityGroup>(Pair.Value));
        }
    }
}

bool FLandscapeSplineHierarchyService::TickAlwaysVisible(float)
{
    if (bAlwaysVisible)
    {
        ApplyAlwaysVisibleToSplineComponents();
    }
    return true;
}

bool FLandscapeSplineHierarchyService::AreEngineHooksAvailable() const
{
    return LSH_WITH_ENGINE_HOOKS != 0;
}

ALandscapeSplineHierarchyMetadata* FLandscapeSplineHierarchyService::FindMetadata(ALandscape* Landscape) const
{
    if (!Landscape)
    {
        return nullptr;
    }
    for (TActorIterator<ALandscapeSplineHierarchyMetadata> It(Landscape->GetWorld()); It; ++It)
    {
        if (It->Landscape == Landscape)
        {
            return *It;
        }
    }
    return nullptr;
}

ALandscapeSplineHierarchyMetadata* FLandscapeSplineHierarchyService::FindOrCreateMetadata(ALandscape* Landscape)
{
    if (!Landscape)
    {
        return nullptr;
    }
    if (ALandscapeSplineHierarchyMetadata* Existing = FindMetadata(Landscape))
    {
        return Existing;
    }

    FActorSpawnParameters Params;
    Params.Name = MakeUniqueObjectName(Landscape->GetLevel(), ALandscapeSplineHierarchyMetadata::StaticClass(), TEXT("LandscapeSplineHierarchy"));
    Params.OverrideLevel = Landscape->GetLevel();
    Params.ObjectFlags |= RF_Transactional;
    ALandscapeSplineHierarchyMetadata* Metadata = Landscape->GetWorld()->SpawnActor<ALandscapeSplineHierarchyMetadata>(Params);
    if (Metadata)
    {
        Metadata->Modify();
        Metadata->Landscape = Landscape;
        Metadata->SetActorLabel(FString::Printf(TEXT("%s - Spline Hierarchy"), *Landscape->GetActorLabel()));
        Metadata->SetIsTemporarilyHiddenInEditor(true);
    }
    return Metadata;
}

ALandscape* FLandscapeSplineHierarchyService::FindLandscapeFor(const UObject* SplineObject) const
{
    const ULandscapeSplinesComponent* Component = SplineObject ? SplineObject->GetTypedOuter<ULandscapeSplinesComponent>() : nullptr;
    AActor* Owner = Component ? Component->GetOwner() : nullptr;
    ILandscapeSplineInterface* SplineOwner = Owner ? Cast<ILandscapeSplineInterface>(Owner) : nullptr;
    ULandscapeInfo* Info = SplineOwner ? SplineOwner->GetLandscapeInfo() : nullptr;
    return Info ? Info->LandscapeActor.Get() : nullptr;
}

ALandscape* FLandscapeSplineHierarchyService::FindCurrentLandscape() const
{
    TArray<ULandscapeSplineControlPoint*> ControlPoints;
    TArray<ULandscapeSplineSegment*> Segments;
    GetSelectedSplineObjects(ControlPoints, Segments);
    if (ControlPoints.Num()) return FindLandscapeFor(ControlPoints[0]);
    if (Segments.Num()) return FindLandscapeFor(Segments[0]);

    if (GEditor)
    {
        for (FSelectionIterator It(*GEditor->GetSelectedActors()); It; ++It)
        {
            if (ALandscape* Landscape = Cast<ALandscape>(*It)) return Landscape;
        }
    }
    return nullptr;
}

void FLandscapeSplineHierarchyService::GetSelectedSplineObjects(TArray<ULandscapeSplineControlPoint*>& OutControlPoints, TArray<ULandscapeSplineSegment*>& OutSegments) const
{
    OutControlPoints.Reset();
    OutSegments.Reset();
    for (TObjectIterator<ULandscapeSplineControlPoint> It; It; ++It)
    {
        if (!It->HasAnyFlags(RF_ClassDefaultObject) && It->IsSplineSelected()) OutControlPoints.Add(*It);
    }
    for (TObjectIterator<ULandscapeSplineSegment> It; It; ++It)
    {
        if (!It->HasAnyFlags(RF_ClassDefaultObject) && It->IsSplineSelected()) OutSegments.Add(*It);
    }
}

bool FLandscapeSplineHierarchyService::SelectSplineElementThroughGeometry(bool bAddToSelection, float ControlPointRadius, float SegmentRadius)
{
    if (!bAlwaysVisible || !GEditor) return false;
    FViewport* Viewport = GEditor->GetActiveViewport();
    FEditorViewportClient* ViewportClient = Viewport ? static_cast<FEditorViewportClient*>(Viewport->GetClient()) : nullptr;
    if (!Viewport || !ViewportClient || !Viewport->HasFocus()) return false;

    FSceneViewFamily ViewFamily(FSceneViewFamily::ConstructionValues(
        Viewport, ViewportClient->GetScene(), ViewportClient->EngineShowFlags)
        .SetRealtimeUpdate(ViewportClient->IsRealtime()));
    TSharedPtr<FSceneView> SceneView = MakeShareable(ViewportClient->CalcSceneView(&ViewFamily));
    if (!SceneView) return false;

    const FVector2D MousePosition(Viewport->GetMouseX(), Viewport->GetMouseY());
    const FIntRect ViewRect(FIntPoint::ZeroValue, Viewport->GetSizeXY());
    ULandscapeSplineControlPoint* ClosestPoint = nullptr;
    double ClosestDistanceSquared = FMath::Square(static_cast<double>(ControlPointRadius));
    for (TObjectIterator<ULandscapeSplineControlPoint> It; It; ++It)
    {
        ULandscapeSplineControlPoint* Point = *It;
        ULandscapeSplinesComponent* Component = Point->GetOuterULandscapeSplinesComponent();
        if (!IsValid(Point) || !IsValid(Component) || Component->GetWorld() != ViewportClient->GetWorld()) continue;
        FVector2D Pixel;
        const FVector WorldPosition = Component->GetComponentTransform().TransformPosition(Point->Location);
        if (!FSceneView::ProjectWorldToScreen(WorldPosition, ViewRect, SceneView->ViewMatrices.GetWorldToClip(), Pixel)) continue;
        const double DistanceSquared = FVector2D::DistSquared(Pixel, MousePosition);
        if (DistanceSquared <= ClosestDistanceSquared)
        {
            ClosestDistanceSquared = DistanceSquared;
            ClosestPoint = Point;
        }
    }
    ULandscapeSplineSegment* ClosestSegment = nullptr;
    double ClosestSegmentDistanceSquared = FMath::Square(static_cast<double>(SegmentRadius));
    for (TObjectIterator<ULandscapeSplineSegment> It; It; ++It)
    {
        ULandscapeSplineSegment* Segment = *It;
        ULandscapeSplinesComponent* Component = Segment->GetOuterULandscapeSplinesComponent();
        if (!IsValid(Segment) || !IsValid(Component) || Component->GetWorld() != ViewportClient->GetWorld()) continue;
        const TArray<FLandscapeSplineInterpPoint>& Points = Segment->GetPoints();
        FVector2D PreviousPixel;
        bool bHasPrevious = false;
        for (const FLandscapeSplineInterpPoint& Point : Points)
        {
            FVector2D Pixel;
            const FVector WorldPosition = Component->GetComponentTransform().TransformPosition(Point.Center);
            if (!FSceneView::ProjectWorldToScreen(WorldPosition, ViewRect, SceneView->ViewMatrices.GetWorldToClip(), Pixel))
            {
                bHasPrevious = false;
                continue;
            }
            if (bHasPrevious)
            {
                const FVector2D Line = Pixel - PreviousPixel;
                const double LineSizeSquared = Line.SizeSquared();
                const double Alpha = LineSizeSquared > UE_DOUBLE_SMALL_NUMBER
                    ? FMath::Clamp(FVector2D::DotProduct(MousePosition - PreviousPixel, Line) / LineSizeSquared, 0.0, 1.0)
                    : 0.0;
                const double DistanceSquared = FVector2D::DistSquared(MousePosition, PreviousPixel + Line * Alpha);
                if (DistanceSquared <= ClosestSegmentDistanceSquared)
                {
                    ClosestSegmentDistanceSquared = DistanceSquared;
                    ClosestSegment = Segment;
                }
            }
            PreviousPixel = Pixel;
            bHasPrevious = true;
        }
    }
    if (!ClosestPoint && !ClosestSegment) return false;

    // Control points win where their larger screen-space hit area overlaps a segment.
    const bool bSelectPoint = ClosestPoint != nullptr;

    TArray<UObject*> PointObjects;
    TArray<UObject*> SegmentObjects;
    if (bAddToSelection)
    {
        TArray<ULandscapeSplineControlPoint*> ExistingPoints;
        TArray<ULandscapeSplineSegment*> ExistingSegments;
        GetSelectedSplineObjects(ExistingPoints, ExistingSegments);
        if (bSelectPoint) for (ULandscapeSplineControlPoint* Point : ExistingPoints) PointObjects.Add(Point);
        else for (ULandscapeSplineSegment* Segment : ExistingSegments) SegmentObjects.Add(Segment);
    }
    if (bSelectPoint) PointObjects.AddUnique(ClosestPoint);
    else SegmentObjects.AddUnique(ClosestSegment);

    if (UObject* Selection = FindNativeSplineSelection())
    {
        ReplaceObjectArrayProperty(Selection, TEXT("SelectedSplineControlPoints"), PointObjects);
        ReplaceObjectArrayProperty(Selection, TEXT("SelectedSplineSegments"), SegmentObjects);
        ReplaceObjectArrayProperty(Selection, TEXT("LinearControlPoints"), {});
        ReplaceObjectArrayProperty(Selection, TEXT("LinearSegments"), {});
    }
    for (TObjectIterator<ULandscapeSplineControlPoint> It; It; ++It) It->SetSplineSelected(PointObjects.Contains(*It));
    for (TObjectIterator<ULandscapeSplineSegment> It; It; ++It) It->SetSplineSelected(SegmentObjects.Contains(*It));
    TArray<UObject*> PropertyObjects = PointObjects;
    PropertyObjects.Append(SegmentObjects);
    FPropertyEditorModule& PropertyModule = FModuleManager::LoadModuleChecked<FPropertyEditorModule>(TEXT("PropertyEditor"));
    PropertyModule.UpdatePropertyViews(PropertyObjects);
    GEditor->RedrawAllViewports(true);
    return true;
}

void FLandscapeSplineHierarchyService::CreateGroupFromSelection(FName SuggestedName)
{
    TArray<ULandscapeSplineControlPoint*> ControlPoints;
    TArray<ULandscapeSplineSegment*> Segments;
    GetSelectedSplineObjects(ControlPoints, Segments);
    UObject* First = ControlPoints.Num() ? static_cast<UObject*>(ControlPoints[0]) : (Segments.Num() ? static_cast<UObject*>(Segments[0]) : nullptr);
    ALandscape* Landscape = FindLandscapeFor(First);
    ExpandSplineSelectionToConnectedMembers(Landscape, ControlPoints, Segments);
    ALandscapeSplineHierarchyMetadata* Metadata = FindOrCreateMetadata(Landscape);
    if (!Metadata || (!ControlPoints.Num() && !Segments.Num()))
    {
        return;
    }

    const FScopedTransaction Transaction(NSLOCTEXT("LandscapeSplineHierarchy", "CreateGroup", "Create Landscape Spline Group"));
    Metadata->Modify();

    for (FLandscapeSplineGroup& Existing : Metadata->Groups)
    {
        Existing.ControlPoints.RemoveAll([&](const ULandscapeSplineControlPoint* Item) { return ControlPoints.Contains(Item); });
        Existing.Segments.RemoveAll([&](const ULandscapeSplineSegment* Item) { return Segments.Contains(Item); });
    }

    FLandscapeSplineGroup& Group = Metadata->Groups.AddDefaulted_GetRef();
    Group.Id = FGuid::NewGuid();
    Group.Name = SuggestedName.IsNone() ? FName(*FString::Printf(TEXT("Spline Group %d"), Metadata->Groups.Num())) : SuggestedName;
    Group.Priority = Metadata->Groups.Num() * 10;
    Group.ControlPoints = ControlPoints;
    Group.Segments = Segments;
    SortGroups(Metadata);
    NotifyHierarchyChanged(Metadata);
}

ALandscapeSplineHierarchyMetadata* FLandscapeSplineHierarchyService::SynchronizeAutomaticSplineGraphs(ALandscape* Landscape)
{
    if (!Landscape) return nullptr;
    ALandscapeSplineHierarchyMetadata* Metadata = FindOrCreateMetadata(Landscape);
    if (!Metadata) return nullptr;

    TArray<ULandscapeSplineControlPoint*> AllPoints;
    for (TObjectIterator<ULandscapeSplineControlPoint> It; It; ++It)
    {
        if (!It->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject) && FindLandscapeFor(*It) == Landscape)
        {
            AllPoints.Add(*It);
        }
    }

    TSet<ULandscapeSplineControlPoint*> Visited;
    TArray<FLandscapeSplineGroup> NewGroups;
    for (ULandscapeSplineControlPoint* Seed : AllPoints)
    {
        if (!IsValid(Seed) || Visited.Contains(Seed)) continue;

        TArray<ULandscapeSplineControlPoint*> Queue{Seed};
        TArray<ULandscapeSplineControlPoint*> GraphPoints;
        TArray<ULandscapeSplineSegment*> GraphSegments;
        Visited.Add(Seed);
        for (int32 QueueIndex = 0; QueueIndex < Queue.Num(); ++QueueIndex)
        {
            ULandscapeSplineControlPoint* Point = Queue[QueueIndex];
            GraphPoints.Add(Point);
            for (const FLandscapeSplineConnection& Connection : Point->ConnectedSegments)
            {
                ULandscapeSplineSegment* Segment = Connection.Segment.Get();
                if (!IsValid(Segment)) continue;
                GraphSegments.AddUnique(Segment);
                for (const FLandscapeSplineSegmentConnection& End : Segment->Connections)
                {
                    ULandscapeSplineControlPoint* Other = End.ControlPoint.Get();
                    if (IsValid(Other) && !Visited.Contains(Other))
                    {
                        Visited.Add(Other);
                        Queue.Add(Other);
                    }
                }
            }
        }

        const FLandscapeSplineGroup* BestOldGroup = nullptr;
        int32 BestOverlap = 0;
        for (const FLandscapeSplineGroup& OldGroup : Metadata->Groups)
        {
            int32 Overlap = 0;
            for (ULandscapeSplineControlPoint* Point : GraphPoints) if (OldGroup.ControlPoints.Contains(Point)) ++Overlap;
            if (Overlap > BestOverlap) { BestOverlap = Overlap; BestOldGroup = &OldGroup; }
        }

        FLandscapeSplineGroup& Group = NewGroups.AddDefaulted_GetRef();
        Group.Id = BestOldGroup ? BestOldGroup->Id : FGuid::NewGuid();
        Group.Name = BestOldGroup ? BestOldGroup->Name : FName(*FString::Printf(TEXT("Spline %d"), NewGroups.Num()));
        Group.ControlPoints = GraphPoints;
        Group.Segments = GraphSegments;
    }

    Metadata->Modify();
    Metadata->Groups = MoveTemp(NewGroups);
    Metadata->MarkPackageDirty();
    return Metadata;
}

void FLandscapeSplineHierarchyService::RemoveGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId)
{
    if (!Metadata) return;
    const FScopedTransaction Transaction(NSLOCTEXT("LandscapeSplineHierarchy", "RemoveGroup", "Remove Landscape Spline Group"));
    Metadata->Modify();
    Metadata->Groups.RemoveAll([&](const FLandscapeSplineGroup& Group) { return Group.Id == GroupId; });
    NotifyHierarchyChanged(Metadata);
}

void FLandscapeSplineHierarchyService::SelectGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId)
{
    if (!Metadata) return;
    FLandscapeSplineGroup* Group = Metadata->Groups.FindByPredicate([&](const FLandscapeSplineGroup& Item) { return Item.Id == GroupId; });
    if (!Group || Group->bLocked) return;

    TArray<UObject*> ControlPointObjects;
    TArray<UObject*> SegmentObjects;
    for (ULandscapeSplineControlPoint* Point : Group->ControlPoints) if (IsValid(Point)) ControlPointObjects.Add(Point);
    for (ULandscapeSplineSegment* Segment : Group->Segments) if (IsValid(Segment)) SegmentObjects.Add(Segment);

    if (UObject* Selection = FindNativeSplineSelection())
    {
        ReplaceObjectArrayProperty(Selection, TEXT("SelectedSplineControlPoints"), ControlPointObjects);
        ReplaceObjectArrayProperty(Selection, TEXT("SelectedSplineSegments"), SegmentObjects);
        ReplaceObjectArrayProperty(Selection, TEXT("LinearControlPoints"), {});
        ReplaceObjectArrayProperty(Selection, TEXT("LinearSegments"), {});
    }

    for (TObjectIterator<ULandscapeSplineControlPoint> It; It; ++It) It->SetSplineSelected(ControlPointObjects.Contains(*It));
    for (TObjectIterator<ULandscapeSplineSegment> It; It; ++It) It->SetSplineSelected(SegmentObjects.Contains(*It));
    if (GEditor) GEditor->RedrawAllViewports(true);
}

void FLandscapeSplineHierarchyService::MoveGroup(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId, int32 Direction)
{
    if (!Metadata || Direction == 0) return;
    SortGroups(Metadata);
    const int32 Index = Metadata->Groups.IndexOfByPredicate([&](const FLandscapeSplineGroup& Group) { return Group.Id == GroupId; });
    const int32 OtherIndex = FMath::Clamp(Index + Direction, 0, Metadata->Groups.Num() - 1);
    if (Index == INDEX_NONE || Index == OtherIndex) return;

    const FScopedTransaction Transaction(NSLOCTEXT("LandscapeSplineHierarchy", "MoveGroup", "Reorder Landscape Spline Group"));
    Metadata->Modify();
    Metadata->Groups.Swap(Index, OtherIndex);
    const int32 High = (Metadata->Groups.Num() - Index) * 10;
    const int32 OtherHigh = (Metadata->Groups.Num() - OtherIndex) * 10;
    Metadata->Groups[Index].Priority = High;
    Metadata->Groups[OtherIndex].Priority = OtherHigh;
    SortGroups(Metadata);
    NotifyHierarchyChanged(Metadata);
}

void FLandscapeSplineHierarchyService::SortGroups(ALandscapeSplineHierarchyMetadata* Metadata)
{
    if (!Metadata) return;
    Metadata->Groups.StableSort([](const FLandscapeSplineGroup& A, const FLandscapeSplineGroup& B) { return A.Priority > B.Priority; });
}

void FLandscapeSplineHierarchyService::NotifyHierarchyChanged(ALandscapeSplineHierarchyMetadata* Metadata)
{
    if (!Metadata) return;

    // Upgrade point-only groups created by version 1.0 and keep every logical
    // group graph-complete whenever the hierarchy changes.
    for (FLandscapeSplineGroup& Group : Metadata->Groups)
    {
        TArray<ULandscapeSplineControlPoint*> ControlPoints;
        TArray<ULandscapeSplineSegment*> Segments;
        for (ULandscapeSplineControlPoint* Point : Group.ControlPoints)
        {
            if (IsValid(Point)) ControlPoints.Add(Point);
        }
        for (ULandscapeSplineSegment* Segment : Group.Segments)
        {
            if (IsValid(Segment)) Segments.Add(Segment);
        }
        ExpandSplineSelectionToConnectedMembers(Metadata->Landscape, ControlPoints, Segments);

        Group.ControlPoints.Reset(ControlPoints.Num());
        for (ULandscapeSplineControlPoint* Point : ControlPoints) Group.ControlPoints.Add(Point);
        Group.Segments.Reset(Segments.Num());
        for (ULandscapeSplineSegment* Segment : Segments) Group.Segments.Add(Segment);
    }

    Metadata->MarkPackageDirty();
    if (Metadata->Landscape)
    {
        // Public-API fallback: native rasterization consumes these arrays in order.
        // Sorting low-to-high makes overlapping segments deterministic. Control points
        // are still rasterized as a separate pass by stock UE; the engine hook removes
        // that remaining cross-pass limitation.
        if (ULandscapeInfo* Info = Metadata->Landscape->GetLandscapeInfo())
        {
            Info->ForAllSplineActors([Metadata](TScriptInterface<ILandscapeSplineInterface> Owner)
            {
                if (ULandscapeSplinesComponent* Component = Owner->GetSplinesComponent())
                {
                    auto PriorityFor = [Metadata](const UObject* Object)
                    {
                        const FLandscapeSplineGroup* Group = Metadata->FindGroupFor(Object);
                        return Group ? Group->Priority : 0;
                    };
                    Component->Modify();
                    Component->GetControlPoints().StableSort([&](const ULandscapeSplineControlPoint& A, const ULandscapeSplineControlPoint& B)
                    {
                        return PriorityFor(&A) < PriorityFor(&B);
                    });
                    Component->GetSegments().StableSort([&](const ULandscapeSplineSegment& A, const ULandscapeSplineSegment& B)
                    {
                        return PriorityFor(&A) < PriorityFor(&B);
                    });
                }
            });
        }
        Metadata->Landscape->RequestSplineLayerUpdate();
        if (ULandscapeInfo* Info = Metadata->Landscape->GetLandscapeInfo())
        {
            Info->ForAllSplineActors([](TScriptInterface<ILandscapeSplineInterface> Owner)
            {
                if (ULandscapeSplinesComponent* Component = Owner->GetSplinesComponent()) Component->MarkRenderStateDirty();
            });
        }
    }
    if (GEditor) GEditor->RedrawAllViewports(true);
}

const FLandscapeSplineGroup* FLandscapeSplineHierarchyService::FindGroupFor(const UObject* Object) const
{
    ALandscape* Landscape = FindLandscapeFor(Object);
    ALandscapeSplineHierarchyMetadata* Metadata = FindMetadata(Landscape);
    return Metadata ? Metadata->FindGroupFor(Object) : nullptr;
}
