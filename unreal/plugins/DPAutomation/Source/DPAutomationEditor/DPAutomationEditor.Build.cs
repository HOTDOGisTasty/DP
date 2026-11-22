using UnrealBuildTool;

public class DPAutomationEditor : ModuleRules
{
    public DPAutomationEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "Landscape",
            "RHI",
            "RenderCore"
        });

        PrivateDependencyModuleNames.AddRange(new[]
        {
            "UnrealEd",
            "MaterialEditor",
            "PCG", "PCGEditor", "StructUtils", "StructUtilsEditor", "DataHierarchyEditor"
        });
    }
}
