#include "OutlinerVisibilityToPlayService.h"

#include "Modules/ModuleManager.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "OutlinerVisibilityToPlay"

class FOutlinerVisibilityToPlayEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        FOutlinerVisibilityToPlayService::Get().Startup();
        UToolMenus::RegisterStartupCallback(
            FSimpleMulticastDelegate::FDelegate::CreateRaw(
                this, &FOutlinerVisibilityToPlayEditorModule::RegisterMenus));
    }

    virtual void ShutdownModule() override
    {
        UToolMenus::UnRegisterStartupCallback(this);
        UToolMenus::UnregisterOwner(this);
        FOutlinerVisibilityToPlayService::Get().Shutdown();
    }

private:
    void RegisterMenus()
    {
        FToolMenuOwnerScoped OwnerScoped(this);
        UToolMenu* Menu = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Tools"));
        FToolMenuSection& Section = Menu->FindOrAddSection(
            TEXT("OutlinerVisibilityToPlay"),
            LOCTEXT("MenuSection", "Play Visibility"));

        Section.AddMenuEntry(
            TEXT("SyncOutlinerVisibilityToPlay"),
            LOCTEXT("SyncVisibilityMenu", "Use Outliner Visibility In Play"),
            LOCTEXT(
                "SyncVisibilityTooltip",
                "Actors hidden with the World Outliner eye are also hidden when Play or Simulate starts."),
            FSlateIcon(),
            FUIAction(
                FExecuteAction::CreateLambda([]
                {
                    FOutlinerVisibilityToPlayService& Service =
                        FOutlinerVisibilityToPlayService::Get();
                    Service.SetEnabled(!Service.IsEnabled());
                }),
                FCanExecuteAction(),
                FIsActionChecked::CreateLambda([]
                {
                    return FOutlinerVisibilityToPlayService::Get().IsEnabled();
                })),
            EUserInterfaceActionType::ToggleButton);
    }
};

IMPLEMENT_MODULE(FOutlinerVisibilityToPlayEditorModule, OutlinerVisibilityToPlayEditor)

#undef LOCTEXT_NAMESPACE
