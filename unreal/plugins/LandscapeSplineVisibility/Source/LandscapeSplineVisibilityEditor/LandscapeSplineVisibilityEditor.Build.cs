using UnrealBuildTool;

public class LandscapeSplineVisibilityEditor : ModuleRules
{
    public LandscapeSplineVisibilityEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "Landscape"
        });

        PrivateDependencyModuleNames.AddRange(new[]
        {
            "ComponentVisualizers",
            "InputCore",
            "LevelEditor",
            "Slate",
            "SlateCore",
            "ToolMenus",
            "UnrealEd"
        });
    }
}
