#include "LandscapeSplineHierarchyService.h"
#include "SLandscapeSplineHierarchy.h"

#include "LevelEditor.h"
#include "Editor.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "ToolMenus.h"
#include "Widgets/Docking/SDockTab.h"

#define LOCTEXT_NAMESPACE "LandscapeSplineHierarchy"

namespace
{
const FName HierarchyTabName(TEXT("LandscapeSplineHierarchy"));

class FLandscapeSplineShortcutProcessor final : public IInputProcessor
{
public:
    virtual void Tick(const float, FSlateApplication&, TSharedRef<ICursor>) override {}
    virtual bool HandleMouseButtonDownEvent(FSlateApplication&, const FPointerEvent& Event) override
    {
        if (Event.GetEffectingButton() != EKeys::LeftMouseButton || Event.IsAltDown() || Event.IsControlDown()) return false;
        return FLandscapeSplineHierarchyService::Get().SelectSplineElementThroughGeometry(Event.IsShiftDown());
    }
};
}

class FLandscapeSplineHierarchyEditorModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        FLandscapeSplineHierarchyService::Get().Startup();
        ShortcutProcessor = MakeShared<FLandscapeSplineShortcutProcessor>();
        FSlateApplication::Get().RegisterInputPreProcessor(ShortcutProcessor, 0);

        FGlobalTabmanager::Get()->RegisterNomadTabSpawner(HierarchyTabName,
            FOnSpawnTab::CreateRaw(this, &FLandscapeSplineHierarchyEditorModule::SpawnHierarchyTab))
            .SetDisplayName(LOCTEXT("TabTitle", "Landscape Spline Outliner"))
            .SetTooltipText(LOCTEXT("TabTooltip", "Lists and selects native Landscape Spline networks."))
            .SetMenuType(ETabSpawnerMenuType::Hidden);

        UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FLandscapeSplineHierarchyEditorModule::RegisterMenus));
    }

    virtual void ShutdownModule() override
    {
        UToolMenus::UnRegisterStartupCallback(this);
        UToolMenus::UnregisterOwner(this);

        FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(HierarchyTabName);
        if (ShortcutProcessor.IsValid() && FSlateApplication::IsInitialized())
        {
            FSlateApplication::Get().UnregisterInputPreProcessor(ShortcutProcessor);
            ShortcutProcessor.Reset();
        }
        FLandscapeSplineHierarchyService::Get().Shutdown();
    }

private:
    TSharedPtr<FLandscapeSplineShortcutProcessor> ShortcutProcessor;
    TSharedRef<SDockTab> SpawnHierarchyTab(const FSpawnTabArgs&)
    {
        return SNew(SDockTab).TabRole(ETabRole::NomadTab)[SNew(SLandscapeSplineHierarchy)];
    }

    void RegisterMenus()
    {
        FToolMenuOwnerScoped OwnerScoped(this);
        UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
        FToolMenuSection& Section = Menu->FindOrAddSection(TEXT("LandscapeSplineHierarchy"), LOCTEXT("MenuSection", "Landscape Splines"));

        Section.AddMenuEntry(
            TEXT("OpenLandscapeSplineHierarchy"),
            LOCTEXT("OpenHierarchy", "Landscape Spline Outliner"),
            LOCTEXT("OpenHierarchyTooltip", "Open the automatic list of native Landscape Spline networks."),
            FSlateIcon(),
            FUIAction(FExecuteAction::CreateLambda([] { FGlobalTabmanager::Get()->TryInvokeTab(HierarchyTabName); })));

        Section.AddMenuEntry(
            TEXT("AlwaysVisibleLandscapeSplines"),
            LOCTEXT("AlwaysVisibleMenu", "Always Visible Splines"),
            LOCTEXT("AlwaysVisibleMenuTooltip", "Draw native Landscape Splines and their hit proxies in the foreground while Manage > Splines is active."),
            FSlateIcon(),
            FUIAction(
                FExecuteAction::CreateLambda([]
                {
                    FLandscapeSplineHierarchyService& Service = FLandscapeSplineHierarchyService::Get();
                    Service.SetAlwaysVisibleEnabled(!Service.IsAlwaysVisibleEnabled());
                }),
                FCanExecuteAction(),
                FIsActionChecked::CreateLambda([] { return FLandscapeSplineHierarchyService::Get().IsAlwaysVisibleEnabled(); })),
            EUserInterfaceActionType::ToggleButton);
    }
};

IMPLEMENT_MODULE(FLandscapeSplineHierarchyEditorModule, LandscapeSplineHierarchyEditor)

#undef LOCTEXT_NAMESPACE
