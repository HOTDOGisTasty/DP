#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LandscapeSplineHierarchyTypes.generated.h"

class ALandscape;
class ULandscapeSplineControlPoint;
class ULandscapeSplineSegment;

USTRUCT()
struct FLandscapeSplineGroup
{
    GENERATED_BODY()

    UPROPERTY()
    FGuid Id = FGuid::NewGuid();

    UPROPERTY(EditAnywhere, Category="Spline Group")
    FName Name = TEXT("Spline Group");

    UPROPERTY(EditAnywhere, Category="Spline Group")
    int32 Priority = 0;

    UPROPERTY(EditAnywhere, Category="Spline Group")
    bool bVisible = true;

    UPROPERTY(EditAnywhere, Category="Spline Group")
    bool bLocked = false;

    UPROPERTY()
    TArray<TObjectPtr<ULandscapeSplineControlPoint>> ControlPoints;

    UPROPERTY()
    TArray<TObjectPtr<ULandscapeSplineSegment>> Segments;

    bool Contains(const UObject* Object) const;
    void RemoveInvalidMembers();
};

UCLASS(NotPlaceable, NotBlueprintable)
class LANDSCAPESPLINEHIERARCHYEDITOR_API ALandscapeSplineHierarchyMetadata : public AActor
{
    GENERATED_BODY()

public:
    ALandscapeSplineHierarchyMetadata();

    UPROPERTY()
    TObjectPtr<ALandscape> Landscape = nullptr;

    UPROPERTY()
    TArray<FLandscapeSplineGroup> Groups;

    virtual bool IsEditorOnly() const override { return true; }

    FLandscapeSplineGroup* FindGroupFor(const UObject* Object);
    const FLandscapeSplineGroup* FindGroupFor(const UObject* Object) const;
};
