#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"

class ALandscapeSplineHierarchyMetadata;
class SVerticalBox;

class SLandscapeSplineHierarchy : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SLandscapeSplineHierarchy) {}
    SLATE_END_ARGS()

    void Construct(const FArguments& Arguments);
    void Refresh();

private:
    TSharedRef<SWidget> BuildGroupRow(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId);
    FReply RefreshGraphs();
    FReply ToggleAlwaysVisible();
    ECheckBoxState GetAlwaysVisibleState() const;
    FText GetStatusText() const;

    TSharedPtr<SVerticalBox> GroupBox;
};
