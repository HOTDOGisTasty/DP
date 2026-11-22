using UnrealBuildTool;

public class ActorPaletteSyntyRepairEditor : ModuleRules
{
    public ActorPaletteSyntyRepairEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PrivateDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "Slate",
            "SlateCore",
            "UnrealEd"
        });
    }
}
