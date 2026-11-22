#include "Containers/Ticker.h"
#include "Framework/Docking/TabManager.h"
#include "Modules/ModuleManager.h"
#include "UObject/Class.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogActorPaletteSyntyRepair, Log, All);

namespace ActorPaletteSyntyRepair
{
    constexpr TCHAR OldOverviewPath[] = TEXT("/Game/PolygonWar/Maps/Overview.Overview");
    constexpr TCHAR NewOverviewPath[] = TEXT("/Game/Synty/PolygonWar/Maps/Overview.Overview");

    bool ReplaceStringArrayEntry(UObject* SettingsObject, const FName PropertyName)
    {
        FArrayProperty* ArrayProperty = FindFProperty<FArrayProperty>(SettingsObject->GetClass(), PropertyName);
        FStrProperty* StringProperty = ArrayProperty ? CastField<FStrProperty>(ArrayProperty->Inner) : nullptr;
        if (!ArrayProperty || !StringProperty)
        {
            return false;
        }

        FScriptArrayHelper ArrayHelper(
            ArrayProperty,
            ArrayProperty->ContainerPtrToValuePtr<void>(SettingsObject));

        bool bChanged = false;
        for (int32 Index = 0; Index < ArrayHelper.Num(); ++Index)
        {
            void* ValueAddress = ArrayHelper.GetRawPtr(Index);
            if (StringProperty->GetPropertyValue(ValueAddress) == OldOverviewPath)
            {
                StringProperty->SetPropertyValue(ValueAddress, NewOverviewPath);
                bChanged = true;
            }
        }
        return bChanged;
    }

    bool ReplaceMapEntryPaths(UObject* SettingsObject)
    {
        FArrayProperty* ArrayProperty = FindFProperty<FArrayProperty>(
            SettingsObject->GetClass(),
            TEXT("SettingsPerLevel"));
        FStructProperty* EntryProperty = ArrayProperty ? CastField<FStructProperty>(ArrayProperty->Inner) : nullptr;
        FStrProperty* MapPathProperty = EntryProperty
            ? FindFProperty<FStrProperty>(EntryProperty->Struct, TEXT("MapPath"))
            : nullptr;
        if (!ArrayProperty || !EntryProperty || !MapPathProperty)
        {
            return false;
        }

        FScriptArrayHelper ArrayHelper(
            ArrayProperty,
            ArrayProperty->ContainerPtrToValuePtr<void>(SettingsObject));

        bool bChanged = false;
        for (int32 Index = 0; Index < ArrayHelper.Num(); ++Index)
        {
            void* EntryAddress = ArrayHelper.GetRawPtr(Index);
            if (MapPathProperty->GetPropertyValue_InContainer(EntryAddress) == OldOverviewPath)
            {
                MapPathProperty->SetPropertyValue_InContainer(EntryAddress, NewOverviewPath);
                bChanged = true;
            }
        }
        return bChanged;
    }
}

class FActorPaletteSyntyRepairEditorModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        RetryHandle = FTSTicker::GetCoreTicker().AddTicker(
            FTickerDelegate::CreateRaw(this, &FActorPaletteSyntyRepairEditorModule::TryRepair),
            0.5f);
    }

    virtual void ShutdownModule() override
    {
        if (RetryHandle.IsValid())
        {
            FTSTicker::GetCoreTicker().RemoveTicker(RetryHandle);
            RetryHandle.Reset();
        }
    }

private:
    bool TryRepair(float)
    {
        ++AttemptCount;
        FModuleManager::Get().LoadModule(TEXT("ActorPalette"));

        UClass* SettingsClass = FindObject<UClass>(
            nullptr,
            TEXT("/Script/ActorPalette.ActorPaletteSettings"));
        if (!SettingsClass)
        {
            return AttemptCount < 20;
        }

        UObject* SettingsObject = SettingsClass->GetDefaultObject();
        if (!SettingsObject)
        {
            return AttemptCount < 20;
        }

        bool bChanged = ActorPaletteSyntyRepair::ReplaceMapEntryPaths(SettingsObject);
        bChanged |= ActorPaletteSyntyRepair::ReplaceStringArrayEntry(SettingsObject, TEXT("RecentlyUsedList"));
        bChanged |= ActorPaletteSyntyRepair::ReplaceStringArrayEntry(SettingsObject, TEXT("MostRecentLevelByTab"));
        bChanged |= ActorPaletteSyntyRepair::ReplaceStringArrayEntry(SettingsObject, TEXT("FavoritesList"));

        if (bChanged)
        {
            SettingsObject->SaveConfig();
            UE_LOG(
                LogActorPaletteSyntyRepair,
                Display,
                TEXT("Repaired Actor Palette Overview path: %s -> %s"),
                ActorPaletteSyntyRepair::OldOverviewPath,
                ActorPaletteSyntyRepair::NewOverviewPath);
            FGlobalTabmanager::Get()->TryInvokeTab(FTabId(TEXT("ActorPaletteTab1")));
        }

        RetryHandle.Reset();
        return false;
    }

    FTSTicker::FDelegateHandle RetryHandle;
    int32 AttemptCount = 0;
};

IMPLEMENT_MODULE(FActorPaletteSyntyRepairEditorModule, ActorPaletteSyntyRepairEditor)
