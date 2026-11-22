#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "DPAutomationLibrary.generated.h"

class ALandscape;
class UMaterial;
class UMaterialInterface;

UCLASS()
class DPAUTOMATIONEDITOR_API UDPAutomationLibrary final : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Groups the existing OpenArea parameters without changing values or IDs. Does not save. */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation|PCG")
    static FString OrganizeOpenAreaParameters();

    /** Groups normal forest lists and controls; preserves values and IDs. */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation|PCG")
    static FString OrganizeNormalForestParameters();

    /**
     * Creates a compact, centered Landscape in the current editor world.
     * The height field contains a flat area, a smooth slope and a shallow ridge
     * so material displacement can be compared under controlled conditions.
     */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation")
    static ALandscape* CreateTestLandscape(
        int32 ComponentCountX = 2,
        int32 ComponentCountY = 2,
        int32 SectionsPerComponent = 1,
        int32 QuadsPerSection = 63,
        float ScaleXY = 100.0f,
        float ScaleZ = 100.0f,
        UMaterialInterface* LandscapeMaterial = nullptr);

    /** Builds or force-rebuilds the Nanite representation of one Landscape. */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation")
    static bool BuildLandscapeNanite(ALandscape* Landscape, bool bForceRebuild = true);

    /**
     * Returns read-only, engine-ground-truth material diagnostics as JSON.
     * This is intentionally narrow and is used by headless validation scripts.
     */
    UFUNCTION(BlueprintPure, Category = "DP|Automation")
    static FString GetMaterialDiagnostics(UMaterialInterface* Material);

    /**
     * Inserts an editor-only, post-blend displacement fade into the production
     * Landscape material. All material attributes are passed through unchanged;
     * only Displacement is multiplied by the final Stone blend alpha.
     *
     * The function recompiles but deliberately does not save the material, so a
     * visual test can be rejected without touching the on-disk production asset.
     */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation|Material")
    static bool ApplyStonePostBlendDisplacementFade(
        UMaterial* Material,
        float FadeStart = 0.15f,
        float FadeFull = 0.85f);

    /** Removes the post-blend displacement fade and recompiles without saving. */
    UFUNCTION(BlueprintCallable, Category = "DP|Automation|Material")
    static bool RemoveStonePostBlendDisplacementFade(UMaterial* Material);
};
