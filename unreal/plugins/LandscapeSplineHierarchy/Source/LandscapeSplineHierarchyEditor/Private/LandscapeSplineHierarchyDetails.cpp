#include "LandscapeSplineHierarchyDetails.h"

#include "SLandscapeSplineHierarchy.h"
#include "DetailCategoryBuilder.h"
#include "DetailLayoutBuilder.h"
#include "DetailWidgetRow.h"

TSharedRef<IDetailCustomization> FLandscapeSplineHierarchyDetails::MakeInstance()
{
    return MakeShared<FLandscapeSplineHierarchyDetails>();
}

void FLandscapeSplineHierarchyDetails::CustomizeDetails(IDetailLayoutBuilder& DetailBuilder)
{
    IDetailCategoryBuilder& Category = DetailBuilder.EditCategory(
        TEXT("Spline Hierarchy"),
        NSLOCTEXT("LandscapeSplineHierarchy", "DetailsCategory", "Spline Hierarchy"),
        ECategoryPriority::Important);

    Category.AddCustomRow(NSLOCTEXT("LandscapeSplineHierarchy", "DetailsFilter", "Spline Hierarchy Priority Group"))
        .WholeRowContent()
        .MinDesiredWidth(500)
        [SNew(SLandscapeSplineHierarchy)];
}
