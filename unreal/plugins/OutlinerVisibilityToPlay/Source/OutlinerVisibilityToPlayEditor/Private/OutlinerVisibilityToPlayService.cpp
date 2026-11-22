#include "OutlinerVisibilityToPlayService.h"

#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "LevelEditor.h"
#include "Modules/ModuleManager.h"
#include "GameFramework/Actor.h"
#include "Misc/ConfigCacheIni.h"
#include "Widgets/Docking/SDockTab.h"

DEFINE_LOG_CATEGORY_STATIC(LogOutlinerVisibilityToPlay, Log, All);

namespace
{
const TCHAR* SettingsSection = TEXT("/Script/OutlinerVisibilityToPlayEditor.Settings");
}

FOutlinerVisibilityToPlayService& FOutlinerVisibilityToPlayService::Get()
{
    static FOutlinerVisibilityToPlayService Instance;
    return Instance;
}

void FOutlinerVisibilityToPlayService::Startup()
{
    GConfig->GetBool(SettingsSection, TEXT("Enabled"), bEnabled, GEditorPerProjectIni);
    GConfig->GetBool(
        SettingsSection,
        TEXT("GuardSceneOutlinerDuringPIE"),
        bGuardSceneOutlinerDuringPIE,
        GEditorPerProjectIni);

    PreBeginPIEHandle = FEditorDelegates::PreBeginPIE.AddRaw(
        this, &FOutlinerVisibilityToPlayService::HandlePreBeginPIE);
    PostPIEStartedHandle = FEditorDelegates::PostPIEStarted.AddRaw(
        this, &FOutlinerVisibilityToPlayService::HandlePostPIEStarted);
    EndPIEHandle = FEditorDelegates::EndPIE.AddRaw(
        this, &FOutlinerVisibilityToPlayService::HandleEndPIE);
}

void FOutlinerVisibilityToPlayService::Shutdown()
{
    if (PreBeginPIEHandle.IsValid())
    {
        FEditorDelegates::PreBeginPIE.Remove(PreBeginPIEHandle);
        PreBeginPIEHandle.Reset();
    }
    if (PostPIEStartedHandle.IsValid())
    {
        FEditorDelegates::PostPIEStarted.Remove(PostPIEStartedHandle);
        PostPIEStartedHandle.Reset();
    }
    if (EndPIEHandle.IsValid())
    {
        FEditorDelegates::EndPIE.Remove(EndPIEHandle);
        EndPIEHandle.Reset();
    }

    HiddenEditorActors.Reset();
}

bool FOutlinerVisibilityToPlayService::IsEnabled() const
{
    return bEnabled;
}

void FOutlinerVisibilityToPlayService::SetEnabled(const bool bInEnabled)
{
    if (bEnabled == bInEnabled)
    {
        return;
    }

    bEnabled = bInEnabled;
    GConfig->SetBool(SettingsSection, TEXT("Enabled"), bEnabled, GEditorPerProjectIni);
    GConfig->Flush(false, GEditorPerProjectIni);

    if (!bEnabled)
    {
        HiddenEditorActors.Reset();
    }
}

void FOutlinerVisibilityToPlayService::HandlePreBeginPIE(bool)
{
    HiddenEditorActors.Reset();

    if (bEnabled)
    {
        CaptureHiddenEditorActors();
    }

    if (bGuardSceneOutlinerDuringPIE)
    {
        CloseSceneOutlinerTabsForPIE();
    }
}

void FOutlinerVisibilityToPlayService::HandlePostPIEStarted(bool)
{
    if (!bEnabled)
    {
        return;
    }

    ApplyHiddenStateToPIEActors();
}

void FOutlinerVisibilityToPlayService::HandleEndPIE(bool)
{
    HiddenEditorActors.Reset();
    RestoreSceneOutlinerTabsAfterPIE();
}

void FOutlinerVisibilityToPlayService::CaptureHiddenEditorActors()
{
    if (!GEngine)
    {
        return;
    }

    for (const FWorldContext& Context : GEngine->GetWorldContexts())
    {
        UWorld* World = Context.World();
        if (!World || World->WorldType != EWorldType::Editor)
        {
            continue;
        }

        for (TActorIterator<AActor> It(World); It; ++It)
        {
            AActor* Actor = *It;
            if (IsValid(Actor)
                && !Actor->HasAnyFlags(RF_ClassDefaultObject | RF_ArchetypeObject)
                && Actor->IsTemporarilyHiddenInEditor(true))
            {
                HiddenEditorActors.Add(TWeakObjectPtr<AActor>(Actor));
            }
        }
    }

    UE_LOG(
        LogOutlinerVisibilityToPlay,
        Log,
        TEXT("Captured %d actor(s) hidden with the World Outliner eye."),
        HiddenEditorActors.Num());
}

void FOutlinerVisibilityToPlayService::ApplyHiddenStateToPIEActors()
{
    if (!GEditor || HiddenEditorActors.IsEmpty())
    {
        return;
    }

    int32 AppliedCount = 0;

    // Resolve only the actors captured from the editor world. This avoids
    // walking the live PIE actor set while the World Outliner is rebuilding
    // its tree at PIE startup.
    for (const TWeakObjectPtr<AActor>& WeakEditorActor : HiddenEditorActors)
    {
        AActor* EditorActor = WeakEditorActor.Get();
        if (!IsValid(EditorActor))
        {
            continue;
        }

        AActor* PIEActor = EditorUtilities::GetSimWorldCounterpartActor(EditorActor);
        if (!IsValid(PIEActor))
        {
            continue;
        }

        // Only force hidden actors to hidden. Never force visible actors to
        // visible, because that would overwrite intentional gameplay state.
        PIEActor->SetActorHiddenInGame(true);
        ++AppliedCount;
    }

    UE_LOG(
        LogOutlinerVisibilityToPlay,
        Verbose,
        TEXT("Applied Outliner visibility to %d PIE actor counterpart(s)."),
        AppliedCount);
}

void FOutlinerVisibilityToPlayService::CloseSceneOutlinerTabsForPIE()
{
    ClosedSceneOutlinerTabs.Reset();

    if (!FModuleManager::Get().IsModuleLoaded(TEXT("LevelEditor")))
    {
        return;
    }

    FLevelEditorModule& LevelEditorModule =
        FModuleManager::GetModuleChecked<FLevelEditorModule>(TEXT("LevelEditor"));
    const TSharedPtr<FTabManager> TabManager = LevelEditorModule.GetLevelEditorTabManager();
    if (!TabManager.IsValid())
    {
        return;
    }

    const FName SceneOutlinerTabIds[] = {
        LevelEditorTabIds::LevelEditorSceneOutliner,
        LevelEditorTabIds::LevelEditorSceneOutliner2,
        LevelEditorTabIds::LevelEditorSceneOutliner3,
        LevelEditorTabIds::LevelEditorSceneOutliner4
    };

    for (const FName& TabId : SceneOutlinerTabIds)
    {
        if (const TSharedPtr<SDockTab> Tab = TabManager->FindExistingLiveTab(TabId))
        {
            ClosedSceneOutlinerTabs.Add(TabId);
            Tab->RequestCloseTab();
        }
    }

    UE_LOG(
        LogOutlinerVisibilityToPlay,
        Log,
        TEXT("Closed %d Scene Outliner tab(s) before PIE to avoid UE 5.8 null-level pinning crash."),
        ClosedSceneOutlinerTabs.Num());
}

void FOutlinerVisibilityToPlayService::RestoreSceneOutlinerTabsAfterPIE()
{
    if (ClosedSceneOutlinerTabs.IsEmpty()
        || !FModuleManager::Get().IsModuleLoaded(TEXT("LevelEditor")))
    {
        ClosedSceneOutlinerTabs.Reset();
        return;
    }

    FLevelEditorModule& LevelEditorModule =
        FModuleManager::GetModuleChecked<FLevelEditorModule>(TEXT("LevelEditor"));
    const TSharedPtr<FTabManager> TabManager = LevelEditorModule.GetLevelEditorTabManager();
    if (TabManager.IsValid())
    {
        for (const FName& TabId : ClosedSceneOutlinerTabs)
        {
            TabManager->TryInvokeTab(TabId);
        }
    }

    ClosedSceneOutlinerTabs.Reset();
}
