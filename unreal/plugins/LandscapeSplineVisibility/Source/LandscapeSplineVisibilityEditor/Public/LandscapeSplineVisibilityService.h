#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"

class ULandscapeSplinesComponent;
class USplineComponent;
class UPackage;
class UCanvas;
class APlayerController;
class FObjectPreSaveContext;
class IInputProcessor;
struct FPointerEvent;

class LANDSCAPESPLINEVISIBILITYEDITOR_API FLandscapeSplineVisibilityService
{
public:
    static FLandscapeSplineVisibilityService& Get();

    void Startup();
    void Shutdown();

    bool IsAlwaysVisibleEnabled() const;
    void SetAlwaysVisibleEnabled(bool bEnabled);
    const TArray<TWeakObjectPtr<USplineComponent>>& GetLandmassSplineComponents() const;

private:
    friend class FLandmassSplineInputProcessor;

    void ApplyToLoadedSplineComponents();
    void RefreshLandmassSplineComponents();
    void RestoreSplineComponentDepthPriorityGroups();
    void DrawLandmassSplineOverlay(UCanvas* Canvas, APlayerController* PlayerController);
    void HandlePreSavePackage(UPackage* Package, FObjectPreSaveContext SaveContext);
    bool TrySelectLandmassSplinePoint(const FPointerEvent& MouseEvent);
    bool Tick(float DeltaTime);

    bool bAlwaysVisible = true;
    TMap<TWeakObjectPtr<ULandscapeSplinesComponent>, uint8> OriginalDepthPriorityGroups;
    TArray<TWeakObjectPtr<USplineComponent>> LandmassSplineComponents;
    FTSTicker::FDelegateHandle TickerHandle;
    FDelegateHandle PreSavePackageHandle;
    FDelegateHandle DebugDrawHandle;
    TSharedPtr<IInputProcessor> InputProcessor;
};
