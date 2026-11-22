#include "LandscapeSplineVisibilityService.h"

#include "LandscapeSplinesComponent.h"

#include "Components/SplineComponent.h"
#include "ComponentVisualizerManager.h"
#include "Debug/DebugDrawService.h"
#include "Editor.h"
#include "Editor/UnrealEdEngine.h"
#include "EditorViewportClient.h"
#include "Engine/Canvas.h"
#include "Engine/EngineTypes.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Actor.h"
#include "Input/Events.h"
#include "LevelEditorViewport.h"
#include "Misc/ConfigCacheIni.h"
#include "SceneInterface.h"
#include "SceneView.h"
#include "Slate/SceneViewport.h"
#include "SplineComponentVisualizer.h"
#include "UnrealEdGlobals.h"
#include "UObject/ObjectSaveContext.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"

namespace
{
const TCHAR* SettingsSection = TEXT("/Script/LandscapeSplineVisibilityEditor.Settings");
constexpr float LandmassPointHitRadius = 14.0f;

bool ProjectVisibleWorldPoint(
    const FSceneView* View,
    const FVector& WorldPoint,
    FVector2D& OutPixelLocation)
{
    if (!View)
    {
        return false;
    }

    // FSceneView::WorldToPixel intentionally mirrors points whose clip-space W
    // is negative so editor manipulators remain usable when the camera is very
    // close. That behavior is wrong for our persistent overlay: points behind
    // the camera then appear to fly across the viewport while looking around.
    const FVector4 ClipPoint = View->WorldToScreen(WorldPoint);
    return ClipPoint.W > UE_KINDA_SMALL_NUMBER
        && View->ScreenToPixel(ClipPoint, OutPixelLocation);
}
}

class FLandmassSplineInputProcessor final : public IInputProcessor
{
public:
    explicit FLandmassSplineInputProcessor(FLandscapeSplineVisibilityService& InService)
        : Service(InService)
    {
    }

    virtual void Tick(const float, FSlateApplication&, TSharedRef<ICursor>) override
    {
    }

    virtual bool HandleMouseButtonDownEvent(
        FSlateApplication&,
        const FPointerEvent& MouseEvent) override
    {
        if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton
            || MouseEvent.IsAltDown())
        {
            return false;
        }

        return Service.TrySelectLandmassSplinePoint(MouseEvent);
    }

    virtual const TCHAR* GetDebugName() const override
    {
        return TEXT("LandmassSplinePointPicker");
    }

private:
    FLandscapeSplineVisibilityService& Service;
};

FLandscapeSplineVisibilityService& FLandscapeSplineVisibilityService::Get()
{
    static FLandscapeSplineVisibilityService Instance;
    return Instance;
}

void FLandscapeSplineVisibilityService::Startup()
{
    // The plugin is intentionally enabled by default. If the user has changed the
    // setting before, the per-project editor preference wins.
    GConfig->GetBool(SettingsSection, TEXT("AlwaysVisibleSplines"), bAlwaysVisible, GEditorPerProjectIni);

    PreSavePackageHandle = UPackage::PreSavePackageWithContextEvent.AddRaw(
        this, &FLandscapeSplineVisibilityService::HandlePreSavePackage);

    // Do not bind the Landmass overlay to the "Splines" show flag. Landmass
    // toggles its native spline visualization with the actor selection and in
    // some editor view configurations that flag is not evaluated consistently
    // for an unselected Blueprint brush. ModeWidgets is the stable editor-only
    // overlay pass used by the normal level-editor gizmos. The callback still
    // filters to EWorldType::Editor below, so it never draws in PIE or a game.
    DebugDrawHandle = UDebugDrawService::Register(
        TEXT("ModeWidgets"),
        FDebugDrawDelegate::CreateRaw(this, &FLandscapeSplineVisibilityService::DrawLandmassSplineOverlay));
    TickerHandle = FTSTicker::GetCoreTicker().AddTicker(
        FTickerDelegate::CreateRaw(this, &FLandscapeSplineVisibilityService::Tick), 0.5f);

    if (FSlateApplication::IsInitialized())
    {
        InputProcessor = MakeShared<FLandmassSplineInputProcessor>(*this);
        FSlateApplication::Get().RegisterInputPreProcessor(InputProcessor);
    }

    if (bAlwaysVisible)
    {
        ApplyToLoadedSplineComponents();
    }
}

void FLandscapeSplineVisibilityService::Shutdown()
{
    if (InputProcessor.IsValid() && FSlateApplication::IsInitialized())
    {
        FSlateApplication::Get().UnregisterInputPreProcessor(InputProcessor);
        InputProcessor.Reset();
    }

    if (TickerHandle.IsValid())
    {
        FTSTicker::RemoveTicker(TickerHandle);
        TickerHandle.Reset();
    }
    if (PreSavePackageHandle.IsValid())
    {
        UPackage::PreSavePackageWithContextEvent.Remove(PreSavePackageHandle);
        PreSavePackageHandle.Reset();
    }
    if (DebugDrawHandle.IsValid())
    {
        UDebugDrawService::Unregister(DebugDrawHandle);
        DebugDrawHandle.Reset();
    }

    RestoreSplineComponentDepthPriorityGroups();
}

bool FLandscapeSplineVisibilityService::TrySelectLandmassSplinePoint(
    const FPointerEvent& MouseEvent)
{
    if (!bAlwaysVisible
        || !GEditor
        || GEditor->PlayWorld
        || !GUnrealEd
        || !GCurrentLevelEditingViewportClient)
    {
        return false;
    }

    FViewport* Viewport = GEditor->GetActiveViewport();
    FSceneViewport* SceneViewport = Viewport ? Viewport->AsSceneViewport() : nullptr;
    if (!Viewport || !SceneViewport
        || !SceneViewport->GetCachedGeometry().IsUnderLocation(MouseEvent.GetScreenSpacePosition()))
    {
        return false;
    }

    FEditorViewportClient* ViewportClient = GCurrentLevelEditingViewportClient;
    if (!ViewportClient->IsLevelEditorClient())
    {
        return false;
    }

    const FVector2D LocalMouse = SceneViewport->GetCachedGeometry().AbsoluteToLocal(
        MouseEvent.GetScreenSpacePosition());
    const FVector2D LocalSize = SceneViewport->GetCachedGeometry().GetLocalSize();
    const FIntPoint ViewportSize = Viewport->GetSizeXY();
    if (LocalSize.X <= UE_KINDA_SMALL_NUMBER || LocalSize.Y <= UE_KINDA_SMALL_NUMBER)
    {
        return false;
    }

    const FVector2D PixelMouse(
        LocalMouse.X * static_cast<double>(ViewportSize.X) / LocalSize.X,
        LocalMouse.Y * static_cast<double>(ViewportSize.Y) / LocalSize.Y);
    if (PixelMouse.X < 0.0 || PixelMouse.Y < 0.0
        || PixelMouse.X >= ViewportSize.X || PixelMouse.Y >= ViewportSize.Y)
    {
        return false;
    }

    FSceneViewFamilyContext ViewFamily(
        FSceneViewFamily::ConstructionValues(
            Viewport,
            ViewportClient->GetScene(),
            ViewportClient->EngineShowFlags)
        .SetRealtimeUpdate(ViewportClient->IsRealtime()));
    const FSceneView* View = ViewportClient->CalcSceneView(&ViewFamily);
    if (!View || !View->Family || !View->Family->Scene)
    {
        return false;
    }

    UWorld* ViewWorld = View->Family->Scene->GetWorld();
    USplineComponent* BestSpline = nullptr;
    int32 BestPointIndex = INDEX_NONE;
    double BestScreenDistanceSquared = FMath::Square(static_cast<double>(LandmassPointHitRadius));
    double BestWorldDistanceSquared = TNumericLimits<double>::Max();

    for (const TWeakObjectPtr<USplineComponent>& WeakComponent : LandmassSplineComponents)
    {
        USplineComponent* Spline = WeakComponent.Get();
        AActor* OwnerActor = Spline ? Spline->GetOwner() : nullptr;
        if (!Spline
            || !OwnerActor
            || Spline->GetWorld() != ViewWorld
            || !Spline->IsRegistered()
            || OwnerActor->IsHiddenEd())
        {
            continue;
        }

        for (int32 PointIndex = 0; PointIndex < Spline->GetNumberOfSplinePoints(); ++PointIndex)
        {
            const FVector WorldPoint = Spline->GetLocationAtSplinePoint(
                PointIndex,
                ESplineCoordinateSpace::World);
            FVector2D ScreenPoint;
            if (!ProjectVisibleWorldPoint(View, WorldPoint, ScreenPoint))
            {
                continue;
            }

            const double ScreenDistanceSquared = FVector2D::DistSquared(PixelMouse, ScreenPoint);
            const double WorldDistanceSquared = FVector::DistSquared(View->ViewLocation, WorldPoint);
            if (ScreenDistanceSquared < BestScreenDistanceSquared
                || (FMath::IsNearlyEqual(ScreenDistanceSquared, BestScreenDistanceSquared)
                    && WorldDistanceSquared < BestWorldDistanceSquared))
            {
                BestSpline = Spline;
                BestPointIndex = PointIndex;
                BestScreenDistanceSquared = ScreenDistanceSquared;
                BestWorldDistanceSquared = WorldDistanceSquared;
            }
        }
    }

    if (!BestSpline || BestPointIndex == INDEX_NONE)
    {
        return false;
    }

    HSplineKeyProxy SplinePointProxy(BestSpline, BestPointIndex);
    FViewportClick Click(
        View,
        ViewportClient,
        EKeys::LeftMouseButton,
        IE_Pressed,
        FMath::RoundToInt(PixelMouse.X),
        FMath::RoundToInt(PixelMouse.Y));

    const bool bHandled = GUnrealEd->ComponentVisManager.HandleClick(
        ViewportClient,
        &SplinePointProxy,
        Click);
    if (bHandled)
    {
        Viewport->InvalidateHitProxy();
        GEditor->RedrawAllViewports(true);
    }
    return bHandled;
}

bool FLandscapeSplineVisibilityService::IsAlwaysVisibleEnabled() const
{
    return bAlwaysVisible;
}

void FLandscapeSplineVisibilityService::SetAlwaysVisibleEnabled(bool bEnabled)
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
        ApplyToLoadedSplineComponents();
    }
    else
    {
        RestoreSplineComponentDepthPriorityGroups();
        LandmassSplineComponents.Reset();
    }

    if (GEditor)
    {
        GEditor->RedrawAllViewports(true);
    }
}

const TArray<TWeakObjectPtr<USplineComponent>>& FLandscapeSplineVisibilityService::GetLandmassSplineComponents() const
{
    return LandmassSplineComponents;
}

void FLandscapeSplineVisibilityService::ApplyToLoadedSplineComponents()
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

        const TWeakObjectPtr<ULandscapeSplinesComponent> Key(Component);
        if (!OriginalDepthPriorityGroups.Contains(Key))
        {
            OriginalDepthPriorityGroups.Add(Key, static_cast<uint8>(Component->GetStaticDepthPriorityGroup()));
        }

        if (Component->GetStaticDepthPriorityGroup() != SDPG_Foreground)
        {
            // The stock Landscape spline scene proxy retains Unreal's native hit
            // proxies. This plugin only changes editor draw priority; it never
            // synthesizes clicks or modifies LandscapeSplineSelection.
            Component->SetDepthPriorityGroup(SDPG_Foreground);
        }
    }

    RefreshLandmassSplineComponents();
}

void FLandscapeSplineVisibilityService::RefreshLandmassSplineComponents()
{
    LandmassSplineComponents.Reset();

    for (TObjectIterator<USplineComponent> It; It; ++It)
    {
        USplineComponent* Component = *It;
        AActor* Owner = Component ? Component->GetOwner() : nullptr;
        UWorld* World = Component ? Component->GetWorld() : nullptr;
        if (!IsValid(Component)
            || Component->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject)
            || !Owner
            || !World
            || World->WorldType != EWorldType::Editor)
        {
            continue;
        }

        bool bIsLandmassBrush = false;
        for (const UClass* Class = Owner->GetClass(); Class; Class = Class->GetSuperClass())
        {
            const FString ClassPath = Class->GetPathName();
            if (ClassPath.StartsWith(TEXT("/Landmass/"))
                || Class->GetName().Contains(TEXT("CustomBrush_Landmass")))
            {
                bIsLandmassBrush = true;
                break;
            }
        }

        if (bIsLandmassBrush)
        {
            LandmassSplineComponents.Add(Component);
        }
    }
}

void FLandscapeSplineVisibilityService::RestoreSplineComponentDepthPriorityGroups()
{
    for (const TPair<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8>& Pair : OriginalDepthPriorityGroups)
    {
        if (ULandscapeSplinesComponent* Component = Pair.Key.Get())
        {
            Component->SetDepthPriorityGroup(static_cast<ESceneDepthPriorityGroup>(Pair.Value));
        }
    }
    OriginalDepthPriorityGroups.Reset();
    LandmassSplineComponents.Reset();
}

void FLandscapeSplineVisibilityService::DrawLandmassSplineOverlay(
    UCanvas* Canvas,
    APlayerController*)
{
    if (!bAlwaysVisible
        || !Canvas
        || !Canvas->SceneView
        || !Canvas->SceneView->Family
        || !Canvas->SceneView->Family->Scene)
    {
        return;
    }

    UWorld* ViewWorld = Canvas->SceneView->Family->Scene->GetWorld();
    if (!ViewWorld || ViewWorld->WorldType != EWorldType::Editor)
    {
        return;
    }

    constexpr int32 StepsPerSegment = 24;
    constexpr float LineThickness = 2.5f;
    constexpr float PointSize = 10.0f;
    const FLinearColor LineColor(0.05f, 1.0f, 0.28f, 1.0f);
    const FLinearColor PointColor(1.0f, 0.72f, 0.08f, 1.0f);
    const FBox2D ViewportBounds(
        FVector2D(Canvas->SceneView->UnscaledViewRect.Min),
        FVector2D(Canvas->SceneView->UnscaledViewRect.Max));

    for (const TWeakObjectPtr<USplineComponent>& WeakComponent : LandmassSplineComponents)
    {
        USplineComponent* Spline = WeakComponent.Get();
        AActor* OwnerActor = Spline ? Spline->GetOwner() : nullptr;
        if (!Spline
            || !OwnerActor
            || Spline->GetWorld() != ViewWorld
            || !Spline->IsRegistered()
            || OwnerActor->IsHiddenEd())
        {
            continue;
        }

        const int32 NumPoints = Spline->GetNumberOfSplinePoints();
        if (NumPoints <= 0)
        {
            continue;
        }

        for (int32 PointIndex = 0; PointIndex < NumPoints; ++PointIndex)
        {
            FVector2D ScreenPoint;
            if (ProjectVisibleWorldPoint(
                Canvas->SceneView,
                Spline->GetLocationAtSplinePoint(PointIndex, ESplineCoordinateSpace::World),
                ScreenPoint)
                && ViewportBounds.IsInsideOrOn(ScreenPoint))
            {
                Canvas->K2_DrawBox(
                    ScreenPoint - FVector2D(PointSize * 0.5f),
                    FVector2D(PointSize),
                    2.0f,
                    PointColor);
            }
        }

        const int32 NumSegments = Spline->IsClosedLoop() ? NumPoints : NumPoints - 1;
        const float SplineLength = Spline->GetSplineLength();
        for (int32 SegmentIndex = 0; SegmentIndex < NumSegments; ++SegmentIndex)
        {
            const float StartDistance = Spline->GetDistanceAlongSplineAtSplinePoint(SegmentIndex);
            const float EndDistance = SegmentIndex + 1 < NumPoints
                ? Spline->GetDistanceAlongSplineAtSplinePoint(SegmentIndex + 1)
                : SplineLength;
            FVector Previous = Spline->GetLocationAtDistanceAlongSpline(
                StartDistance,
                ESplineCoordinateSpace::World);

            for (int32 Step = 1; Step <= StepsPerSegment; ++Step)
            {
                const float Alpha = static_cast<float>(Step) / StepsPerSegment;
                const FVector Current = Spline->GetLocationAtDistanceAlongSpline(
                    FMath::Lerp(StartDistance, EndDistance, Alpha),
                    ESplineCoordinateSpace::World);
                FVector2D PreviousScreen;
                FVector2D CurrentScreen;
                if (ProjectVisibleWorldPoint(Canvas->SceneView, Previous, PreviousScreen)
                    && ProjectVisibleWorldPoint(Canvas->SceneView, Current, CurrentScreen)
                    && FMath::LineBoxIntersection2D(
                        ViewportBounds,
                        PreviousScreen,
                        CurrentScreen))
                {
                    Canvas->K2_DrawLine(
                        PreviousScreen,
                        CurrentScreen,
                        LineThickness,
                        LineColor);
                }
                Previous = Current;
            }
        }
    }
}

void FLandscapeSplineVisibilityService::HandlePreSavePackage(UPackage* Package, FObjectPreSaveContext)
{
    if (!bAlwaysVisible || !Package)
    {
        return;
    }

    // DepthPriorityGroup is serialized. Restore the original value for the save;
    // the editor ticker reapplies foreground rendering on the next frame.
    for (const TPair<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8>& Pair : OriginalDepthPriorityGroups)
    {
        ULandscapeSplinesComponent* Component = Pair.Key.Get();
        if (Component && Component->GetOutermost() == Package)
        {
            Component->SetDepthPriorityGroup(static_cast<ESceneDepthPriorityGroup>(Pair.Value));
        }
    }
}

bool FLandscapeSplineVisibilityService::Tick(float)
{
    if (bAlwaysVisible)
    {
        ApplyToLoadedSplineComponents();
    }
    return true;
}
