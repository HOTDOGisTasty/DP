#include "DPAutomationLibrary.h"
#include "HAL/IConsoleManager.h"
#include "Materials/Material.h"
#include "Modules/ModuleManager.h"
#include "UObject/SoftObjectPath.h"

namespace
{
    constexpr const TCHAR* ProductionMaterialPath =
        TEXT("/Game/DP/Landscape/Materials/M_Automaterial.M_Automaterial");
}

class FDPAutomationEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        ApplyStoneFadeCommand = MakeUnique<FAutoConsoleCommand>(
            TEXT("DP.Material.ApplyStonePostBlendFade"),
            TEXT("Apply an unsaved Stone post-blend displacement fade. Optional args: FadeStart FadeFull."),
            FConsoleCommandWithArgsDelegate::CreateRaw(this, &FDPAutomationEditorModule::ApplyStoneFade));

        RemoveStoneFadeCommand = MakeUnique<FAutoConsoleCommand>(
            TEXT("DP.Material.RemoveStonePostBlendFade"),
            TEXT("Remove the unsaved Stone post-blend displacement fade."),
            FConsoleCommandDelegate::CreateRaw(this, &FDPAutomationEditorModule::RemoveStoneFade));
    }

    virtual void ShutdownModule() override
    {
        RemoveStoneFadeCommand.Reset();
        ApplyStoneFadeCommand.Reset();
    }

private:
    static UMaterial* LoadProductionMaterial()
    {
        return Cast<UMaterial>(FSoftObjectPath(ProductionMaterialPath).TryLoad());
    }

    void ApplyStoneFade(const TArray<FString>& Args)
    {
        float FadeStart = 0.15f;
        float FadeFull = 0.85f;
        if (Args.Num() > 0)
        {
            FadeStart = FCString::Atof(*Args[0]);
        }
        if (Args.Num() > 1)
        {
            FadeFull = FCString::Atof(*Args[1]);
        }

        UDPAutomationLibrary::ApplyStonePostBlendDisplacementFade(
            LoadProductionMaterial(),
            FadeStart,
            FadeFull);
    }

    void RemoveStoneFade()
    {
        UDPAutomationLibrary::RemoveStonePostBlendDisplacementFade(LoadProductionMaterial());
    }

    TUniquePtr<FAutoConsoleCommand> ApplyStoneFadeCommand;
    TUniquePtr<FAutoConsoleCommand> RemoveStoneFadeCommand;
};

IMPLEMENT_MODULE(FDPAutomationEditorModule, DPAutomationEditor)
