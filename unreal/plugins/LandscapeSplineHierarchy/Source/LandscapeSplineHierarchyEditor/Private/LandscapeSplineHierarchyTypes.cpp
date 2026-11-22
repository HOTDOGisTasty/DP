#include "LandscapeSplineHierarchyTypes.h"

#include "LandscapeSplineControlPoint.h"
#include "LandscapeSplineSegment.h"

bool FLandscapeSplineGroup::Contains(const UObject* Object) const
{
    return ControlPoints.Contains(Object) || Segments.Contains(Object);
}

void FLandscapeSplineGroup::RemoveInvalidMembers()
{
    ControlPoints.RemoveAll([](const ULandscapeSplineControlPoint* Object) { return !IsValid(Object); });
    Segments.RemoveAll([](const ULandscapeSplineSegment* Object) { return !IsValid(Object); });
}

ALandscapeSplineHierarchyMetadata::ALandscapeSplineHierarchyMetadata()
{
    bIsEditorOnlyActor = true;
    SetActorHiddenInGame(true);
    SetCanBeDamaged(false);
}

FLandscapeSplineGroup* ALandscapeSplineHierarchyMetadata::FindGroupFor(const UObject* Object)
{
    return Groups.FindByPredicate([Object](const FLandscapeSplineGroup& Group) { return Group.Contains(Object); });
}

const FLandscapeSplineGroup* ALandscapeSplineHierarchyMetadata::FindGroupFor(const UObject* Object) const
{
    return Groups.FindByPredicate([Object](const FLandscapeSplineGroup& Group) { return Group.Contains(Object); });
}
