#include "LandscapeSplineVisibilityService.h"

#include "Modules/ModuleManager.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "LandscapeSplineVisibility"

class FLandscapeSplineVisibilityEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        FLandscapeSplineVisibilityService::Get().Startup();
        UToolMenus::RegisterStartupCallback(
            FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FLandscapeSplineVisibilityEditorModule::RegisterMenus));
    }

    virtual void ShutdownModule() override
    {
        UToolMenus::UnRegisterStartupCallback(this);
        UToolMenus::UnregisterOwner(this);
        FLandscapeSplineVisibilityService::Get().Shutdown();
    }

private:
    void RegisterMenus()
    {
        FToolMenuOwnerScoped OwnerScoped(this);
        UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
        FToolMenuSection& Section = Menu->FindOrAddSection(
            TEXT("LandscapeSplineVisibility"), LOCTEXT("MenuSection", "Landscape Splines"));

        Section.AddMenuEntry(
            TEXT("AlwaysVisibleLandscapeSplines"),
            LOCTEXT("AlwaysVisibleMenu", "Always Visible Splines"),
            LOCTEXT("AlwaysVisibleMenuTooltip", "Render native Landscape Splines and Landmass brush splines in the editor foreground and make visible Landmass control points directly selectable."),
            FSlateIcon(),
            FUIAction(
                FExecuteAction::CreateLambda([]
                {
                    FLandscapeSplineVisibilityService& Service = FLandscapeSplineVisibilityService::Get();
                    Service.SetAlwaysVisibleEnabled(!Service.IsAlwaysVisibleEnabled());
                }),
                FCanExecuteAction(),
                FIsActionChecked::CreateLambda([]
                {
                    return FLandscapeSplineVisibilityService::Get().IsAlwaysVisibleEnabled();
                })),
            EUserInterfaceActionType::ToggleButton);
    }
};

IMPLEMENT_MODULE(FLandscapeSplineVisibilityEditorModule, LandscapeSplineVisibilityEditor)

#undef LOCTEXT_NAMESPACE
