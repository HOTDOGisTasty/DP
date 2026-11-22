#pragma once

#include "CoreMinimal.h"

class AActor;

class OUTLINERVISIBILITYTOPLAYEDITOR_API FOutlinerVisibilityToPlayService
{
public:
    static FOutlinerVisibilityToPlayService& Get();

    void Startup();
    void Shutdown();

    bool IsEnabled() const;
    void SetEnabled(bool bInEnabled);

private:
    void HandlePreBeginPIE(bool bIsSimulating);
    void HandlePostPIEStarted(bool bIsSimulating);
    void HandleEndPIE(bool bIsSimulating);

    void CaptureHiddenEditorActors();
    void ApplyHiddenStateToPIEActors();
    void CloseSceneOutlinerTabsForPIE();
    void RestoreSceneOutlinerTabsAfterPIE();

    bool bEnabled = true;
    bool bGuardSceneOutlinerDuringPIE = true;
    TSet<TWeakObjectPtr<AActor>> HiddenEditorActors;
    TArray<FName> ClosedSceneOutlinerTabs;

    FDelegateHandle PreBeginPIEHandle;
    FDelegateHandle PostPIEStartedHandle;
    FDelegateHandle EndPIEHandle;
};
