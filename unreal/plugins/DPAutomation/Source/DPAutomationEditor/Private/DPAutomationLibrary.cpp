#include "DPAutomationLibrary.h"

#include "Editor.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeSubsystem.h"
#include "MaterialEditingLibrary.h"
#include "MaterialShared.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionBlendMaterialAttributes.h"
#include "Materials/MaterialExpressionBreakMaterialAttributes.h"
#include "Materials/MaterialExpressionMakeMaterialAttributes.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionSmoothStep.h"
#include "Materials/MaterialInterface.h"
#include "RHI.h"
#include "RHIStrings.h"
#include "RenderUtils.h"

namespace
{
    constexpr int32 LandscapeHeightMidpoint = 32768;
    // UE 5.8 Break Material Attributes output order. The engine class is
    // MinimalAPI, so its otherwise useful PropertyToIOIndexMap is not exported
    // to editor plugins. Keep this narrow mapping beside the graph contract.
    constexpr int32 BreakBaseColor = 0;
    constexpr int32 BreakMetallic = 1;
    constexpr int32 BreakSpecular = 2;
    constexpr int32 BreakRoughness = 3;
    constexpr int32 BreakAnisotropy = 4;
    constexpr int32 BreakEmissiveColor = 5;
    constexpr int32 BreakOpacity = 6;
    constexpr int32 BreakOpacityMask = 7;
    constexpr int32 BreakNormal = 8;
    constexpr int32 BreakTangent = 9;
    constexpr int32 BreakWorldPositionOffset = 10;
    constexpr int32 BreakSubsurfaceColor = 11;
    constexpr int32 BreakClearCoat = 12;
    constexpr int32 BreakClearCoatRoughness = 13;
    constexpr int32 BreakAmbientOcclusion = 14;
    constexpr int32 BreakRefraction = 15;
    constexpr int32 BreakCustomizedUV0 = 16;
    constexpr int32 BreakPixelDepthOffset = 24;
    constexpr int32 BreakShadingModel = 25;
    constexpr int32 BreakDisplacement = 26;
    const FString StoneFadeMarkerPrefix = TEXT("DP Stone PostBlend Displacement Fade");

    template <typename ExpressionType>
    ExpressionType* AddMaterialExpression(
        UMaterial* Material,
        const TCHAR* Description,
        const int32 EditorX,
        const int32 EditorY)
    {
        ExpressionType* Expression = NewObject<ExpressionType>(Material, NAME_None, RF_Transactional);
        Expression->Material = Material;
        Expression->MaterialExpressionEditorX = EditorX;
        Expression->MaterialExpressionEditorY = EditorY;
        Expression->Desc = Description;
        Expression->MaterialExpressionGuid = FGuid::NewGuid();
        Material->GetExpressionCollection().AddExpression(Expression);
        return Expression;
    }

    UMaterialExpression* FindExpressionByObjectName(UMaterial* Material, const FName ObjectName)
    {
        if (!Material)
        {
            return nullptr;
        }

        for (UMaterialExpression* Expression : Material->GetExpressionCollection().Expressions)
        {
            if (Expression && Expression->GetFName() == ObjectName)
            {
                return Expression;
            }
        }

        return nullptr;
    }

    bool HasStoneFadeMarker(const UMaterial* Material)
    {
        if (!Material)
        {
            return false;
        }

        for (const UMaterialExpression* Expression : Material->GetExpressionCollection().Expressions)
        {
            if (Expression && Expression->Desc.StartsWith(StoneFadeMarkerPrefix))
            {
                return true;
            }
        }

        return false;
    }

    bool IsSupportedLandscapeLayout(
        const int32 ComponentCountX,
        const int32 ComponentCountY,
        const int32 SectionsPerComponent,
        const int32 QuadsPerSection)
    {
        const bool bValidComponentCount = ComponentCountX > 0 && ComponentCountX <= 8
            && ComponentCountY > 0 && ComponentCountY <= 8;
        const bool bValidSections = SectionsPerComponent == 1 || SectionsPerComponent == 2;
        const bool bValidQuads = QuadsPerSection == 7 || QuadsPerSection == 15
            || QuadsPerSection == 31 || QuadsPerSection == 63 || QuadsPerSection == 127
            || QuadsPerSection == 255;

        return bValidComponentCount && bValidSections && bValidQuads;
    }
}

ALandscape* UDPAutomationLibrary::CreateTestLandscape(
    const int32 ComponentCountX,
    const int32 ComponentCountY,
    const int32 SectionsPerComponent,
    const int32 QuadsPerSection,
    const float ScaleXY,
    const float ScaleZ,
    UMaterialInterface* LandscapeMaterial)
{
    if (!GEditor || !IsSupportedLandscapeLayout(
            ComponentCountX,
            ComponentCountY,
            SectionsPerComponent,
            QuadsPerSection)
        || ScaleXY <= 0.0f
        || ScaleZ <= 0.0f)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Invalid test Landscape request."));
        return nullptr;
    }

    UWorld* World = GEditor->GetEditorWorldContext().World();
    if (!World)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: The editor world is unavailable."));
        return nullptr;
    }

    const int32 QuadsPerComponent = SectionsPerComponent * QuadsPerSection;
    const int32 SizeX = ComponentCountX * QuadsPerComponent + 1;
    const int32 SizeY = ComponentCountY * QuadsPerComponent + 1;

    FActorSpawnParameters SpawnParameters;
    SpawnParameters.Name = MakeUniqueObjectName(World->PersistentLevel, ALandscape::StaticClass(), TEXT("DP_NaniteTest_Landscape"));
    SpawnParameters.ObjectFlags |= RF_Transactional;

    ALandscape* Landscape = World->SpawnActor<ALandscape>(
        ALandscape::StaticClass(),
        FTransform::Identity,
        SpawnParameters);

    if (!Landscape)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Failed to spawn the test Landscape actor."));
        return nullptr;
    }

    Landscape->Modify();
    Landscape->SetActorLabel(TEXT("DP Nanite Test Landscape"));
    Landscape->SetActorScale3D(FVector(ScaleXY, ScaleXY, ScaleZ));
    Landscape->SetActorLocation(FVector(
        -0.5 * static_cast<double>(SizeX - 1) * ScaleXY,
        -0.5 * static_cast<double>(SizeY - 1) * ScaleXY,
        0.0));
    Landscape->LandscapeMaterial = LandscapeMaterial;

    TArray<uint16> Heights;
    Heights.SetNumUninitialized(SizeX * SizeY);

    for (int32 Y = 0; Y < SizeY; ++Y)
    {
        for (int32 X = 0; X < SizeX; ++X)
        {
            const float NormalizedX = static_cast<float>(X) / static_cast<float>(SizeX - 1);
            const float NormalizedY = static_cast<float>(Y) / static_cast<float>(SizeY - 1);

            const float SlopeAlpha = FMath::SmoothStep(0.42f, 0.88f, NormalizedX);
            const float SlopeHeight = SlopeAlpha * 320.0f;
            const float RidgeDistance = FVector2D::Distance(
                FVector2D(NormalizedX, NormalizedY),
                FVector2D(0.72f, 0.52f));
            const float RidgeHeight = FMath::Clamp(1.0f - RidgeDistance / 0.20f, 0.0f, 1.0f) * 110.0f;

            const int32 EncodedHeight = FMath::Clamp(
                LandscapeHeightMidpoint + FMath::RoundToInt(SlopeHeight + RidgeHeight),
                0,
                MAX_uint16);
            Heights[Y * SizeX + X] = static_cast<uint16>(EncodedHeight);
        }
    }

    TMap<FGuid, TArray<uint16>> HeightmapDataPerLayer;
    HeightmapDataPerLayer.Add(FGuid(), MoveTemp(Heights));

    TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayer;
    MaterialLayerDataPerLayer.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());

    const TArray<FLandscapeLayer> ImportLayers;
    Landscape->Import(
        FGuid::NewGuid(),
        0,
        0,
        SizeX - 1,
        SizeY - 1,
        SectionsPerComponent,
        QuadsPerSection,
        HeightmapDataPerLayer,
        nullptr,
        MaterialLayerDataPerLayer,
        ELandscapeImportAlphamapType::Additive,
        MakeArrayView(ImportLayers));

    ULandscapeInfo* LandscapeInfo = Landscape->CreateLandscapeInfo();
    if (LandscapeInfo)
    {
        LandscapeInfo->UpdateLayerInfoMap(Landscape);
    }

    Landscape->PostEditChange();
    Landscape->MarkPackageDirty();
    World->MarkPackageDirty();

    UE_LOG(
        LogTemp,
        Display,
        TEXT("DPAutomation: Created test Landscape %dx%d vertices (%dx%d components)."),
        SizeX,
        SizeY,
        ComponentCountX,
        ComponentCountY);

    return Landscape;
}

bool UDPAutomationLibrary::BuildLandscapeNanite(ALandscape* Landscape, const bool bForceRebuild)
{
    if (!Landscape)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Cannot build Nanite for a null Landscape."));
        return false;
    }

    UWorld* World = Landscape->GetWorld();
    ULandscapeSubsystem* LandscapeSubsystem = World ? World->GetSubsystem<ULandscapeSubsystem>() : nullptr;
    if (!LandscapeSubsystem)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Landscape subsystem is unavailable."));
        return false;
    }

    TArray<ALandscapeProxy*> ProxiesToBuild;
    ProxiesToBuild.Add(Landscape);

    UE::Landscape::EBuildFlags BuildFlags = UE::Landscape::EBuildFlags::WriteFinalLog;
    if (bForceRebuild)
    {
        BuildFlags |= UE::Landscape::EBuildFlags::ForceRebuild;
    }

    LandscapeSubsystem->BuildNanite(BuildFlags, MakeArrayView(ProxiesToBuild));
    return Landscape->HasNaniteComponents();
}

FString UDPAutomationLibrary::GetMaterialDiagnostics(UMaterialInterface* Material)
{
    if (!Material)
    {
        return TEXT("{\"valid\":false,\"reason\":\"null material\"}");
    }

    const FMaterialResource* Resource = Material->GetMaterialResource(GMaxRHIShaderPlatform);
    const UMaterial* BaseMaterial = Material->GetMaterial();
    const FDisplacementScaling Scaling = Material->GetDisplacementScaling();
    const bool bUsesDisplacement = Resource
        ? Resource->MaterialUsesDisplacement_GameThread()
        : false;

    return FString::Printf(
        TEXT("{\"valid\":true,\"path\":\"%s\",\"resource_valid\":%s,")
        TEXT("\"shader_platform\":\"%s\",\"platform_supports_nanite\":%s,")
        TEXT("\"tessellation_enabled\":%s,\"has_displacement_connected\":%s,")
        TEXT("\"uses_displacement\":%s,")
        TEXT("\"displacement_magnitude\":%.9g,\"displacement_center\":%.9g}"),
        *Material->GetPathName().ReplaceCharWithEscapedChar(),
        Resource ? TEXT("true") : TEXT("false"),
        *LexToString(GMaxRHIShaderPlatform).ReplaceCharWithEscapedChar(),
        DoesPlatformSupportNanite(GMaxRHIShaderPlatform) ? TEXT("true") : TEXT("false"),
        Material->IsTessellationEnabled() ? TEXT("true") : TEXT("false"),
        BaseMaterial && BaseMaterial->HasDisplacementConnected() ? TEXT("true") : TEXT("false"),
        bUsesDisplacement ? TEXT("true") : TEXT("false"),
        Scaling.Magnitude,
        Scaling.Center);
}

bool UDPAutomationLibrary::ApplyStonePostBlendDisplacementFade(
    UMaterial* Material,
    const float FadeStart,
    const float FadeFull)
{
    if (!Material || FadeStart < 0.0f || FadeFull > 1.0f || FadeStart >= FadeFull)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Invalid Stone post-blend fade request."));
        return false;
    }

    if (HasStoneFadeMarker(Material))
    {
        UE_LOG(LogTemp, Warning, TEXT("DPAutomation: Stone post-blend fade already exists on %s."), *Material->GetPathName());
        return false;
    }

    UMaterialExpressionBlendMaterialAttributes* FinalBlend = Cast<UMaterialExpressionBlendMaterialAttributes>(
        FindExpressionByObjectName(Material, TEXT("MaterialExpressionBlendMaterialAttributes_0")));
    UMaterialEditorOnlyData* EditorData = Material->GetEditorOnlyData();

    if (!FinalBlend
        || !FinalBlend->Alpha.Expression
        || !EditorData
        || EditorData->MaterialAttributes.Expression != FinalBlend)
    {
        UE_LOG(
            LogTemp,
            Error,
            TEXT("DPAutomation: Production Stone graph contract does not match %s; no changes made."),
            *Material->GetPathName());
        return false;
    }

    Material->Modify();

    UMaterialExpressionBreakMaterialAttributes* BreakAttributes =
        AddMaterialExpression<UMaterialExpressionBreakMaterialAttributes>(
            Material,
            TEXT("DP Stone PostBlend Displacement Fade | Break final attributes"),
            1350,
            350);
    UMaterialExpressionSmoothStep* Fade = AddMaterialExpression<UMaterialExpressionSmoothStep>(
        Material,
        TEXT("DP Stone PostBlend Displacement Fade | Final Stone coverage"),
        1350,
        100);
    UMaterialExpressionMultiply* FadedDisplacement = AddMaterialExpression<UMaterialExpressionMultiply>(
        Material,
        TEXT("DP Stone PostBlend Displacement Fade | Lower Stone into Grass"),
        1600,
        350);
    UMaterialExpressionMakeMaterialAttributes* MakeAttributes =
        AddMaterialExpression<UMaterialExpressionMakeMaterialAttributes>(
            Material,
            TEXT("DP Stone PostBlend Displacement Fade | Rebuild final attributes"),
            1850,
            350);

    BreakAttributes->MaterialAttributes.Connect(0, FinalBlend);
    Fade->ConstMin = FadeStart;
    Fade->ConstMax = FadeFull;
    // Follow the actual final Blend Material Attributes input rather than a
    // hard-coded upstream HeightLerp. This keeps displacement aligned with the
    // exact visible Grass/Stone line even if the mask graph is refactored.
    Fade->Value.Connect(FinalBlend->Alpha.OutputIndex, FinalBlend->Alpha.Expression);
    FadedDisplacement->A.Connect(BreakDisplacement, BreakAttributes);
    FadedDisplacement->B.Connect(0, Fade);

    MakeAttributes->BaseColor.Connect(BreakBaseColor, BreakAttributes);
    MakeAttributes->Metallic.Connect(BreakMetallic, BreakAttributes);
    MakeAttributes->Specular.Connect(BreakSpecular, BreakAttributes);
    MakeAttributes->Roughness.Connect(BreakRoughness, BreakAttributes);
    MakeAttributes->Anisotropy.Connect(BreakAnisotropy, BreakAttributes);
    MakeAttributes->EmissiveColor.Connect(BreakEmissiveColor, BreakAttributes);
    MakeAttributes->Opacity.Connect(BreakOpacity, BreakAttributes);
    MakeAttributes->OpacityMask.Connect(BreakOpacityMask, BreakAttributes);
    MakeAttributes->Normal.Connect(BreakNormal, BreakAttributes);
    MakeAttributes->Tangent.Connect(BreakTangent, BreakAttributes);
    MakeAttributes->WorldPositionOffset.Connect(BreakWorldPositionOffset, BreakAttributes);
    MakeAttributes->SubsurfaceColor.Connect(BreakSubsurfaceColor, BreakAttributes);
    MakeAttributes->ClearCoat.Connect(BreakClearCoat, BreakAttributes);
    MakeAttributes->ClearCoatRoughness.Connect(BreakClearCoatRoughness, BreakAttributes);
    MakeAttributes->AmbientOcclusion.Connect(BreakAmbientOcclusion, BreakAttributes);
    MakeAttributes->Refraction.Connect(BreakRefraction, BreakAttributes);
    for (int32 UVIndex = 0; UVIndex < UE_ARRAY_COUNT(MakeAttributes->CustomizedUVs); ++UVIndex)
    {
        MakeAttributes->CustomizedUVs[UVIndex].Connect(BreakCustomizedUV0 + UVIndex, BreakAttributes);
    }
    MakeAttributes->PixelDepthOffset.Connect(BreakPixelDepthOffset, BreakAttributes);
    MakeAttributes->ShadingModel.Connect(BreakShadingModel, BreakAttributes);
    MakeAttributes->Displacement.Connect(0, FadedDisplacement);
    EditorData->MaterialAttributes.Connect(0, MakeAttributes);

    Material->MarkPackageDirty();
    const TArray<FString> CompileErrors = UMaterialEditingLibrary::RecompileMaterial(Material);
    if (!CompileErrors.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Stone fade compile reported %d error(s)."), CompileErrors.Num());
        for (const FString& Error : CompileErrors)
        {
            UE_LOG(LogTemp, Error, TEXT("DPAutomation: %s"), *Error);
        }
        return false;
    }

    UE_LOG(
        LogTemp,
        Display,
        TEXT("DPAutomation: Applied unsaved Stone post-blend displacement fade %.3f..%.3f to %s."),
        FadeStart,
        FadeFull,
        *Material->GetPathName());
    return true;
}

bool UDPAutomationLibrary::RemoveStonePostBlendDisplacementFade(UMaterial* Material)
{
    if (!Material)
    {
        return false;
    }

    UMaterialExpression* FinalBlend = FindExpressionByObjectName(
        Material,
        TEXT("MaterialExpressionBlendMaterialAttributes_0"));
    UMaterialEditorOnlyData* EditorData = Material->GetEditorOnlyData();
    if (!FinalBlend || !EditorData)
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Cannot restore the production Stone graph contract."));
        return false;
    }

    TArray<UMaterialExpression*> ExpressionsToRemove;
    for (UMaterialExpression* Expression : Material->GetExpressionCollection().Expressions)
    {
        if (Expression && Expression->Desc.StartsWith(StoneFadeMarkerPrefix))
        {
            ExpressionsToRemove.Add(Expression);
        }
    }

    if (ExpressionsToRemove.IsEmpty())
    {
        UE_LOG(LogTemp, Warning, TEXT("DPAutomation: No Stone post-blend fade exists on %s."), *Material->GetPathName());
        return false;
    }

    Material->Modify();
    EditorData->MaterialAttributes.Connect(0, FinalBlend);
    for (UMaterialExpression* Expression : ExpressionsToRemove)
    {
        Material->GetExpressionCollection().RemoveExpression(Expression);
    }

    Material->MarkPackageDirty();
    const TArray<FString> CompileErrors = UMaterialEditingLibrary::RecompileMaterial(Material);
    if (!CompileErrors.IsEmpty())
    {
        UE_LOG(LogTemp, Error, TEXT("DPAutomation: Restored graph compiled with %d error(s)."), CompileErrors.Num());
        return false;
    }

    UE_LOG(LogTemp, Display, TEXT("DPAutomation: Removed unsaved Stone post-blend displacement fade from %s."), *Material->GetPathName());
    return true;
}
