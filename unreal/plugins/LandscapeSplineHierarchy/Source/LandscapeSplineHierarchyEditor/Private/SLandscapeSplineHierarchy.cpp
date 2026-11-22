#include "SLandscapeSplineHierarchy.h"

#include "LandscapeSplineHierarchyService.h"
#include "LandscapeSplineHierarchyTypes.h"
#include "LandscapeSplineControlPoint.h"
#include "LandscapeSplineSegment.h"

#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSeparator.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Styling/AppStyle.h"

void SLandscapeSplineHierarchy::Construct(const FArguments& Arguments)
{
    ChildSlot
    [
        SNew(SVerticalBox)
        + SVerticalBox::Slot().AutoHeight().Padding(4)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth().Padding(2)
            [
                SNew(SButton)
                .Text(NSLOCTEXT("LandscapeSplineHierarchy", "Refresh", "Refresh Spline List"))
                .OnClicked(this, &SLandscapeSplineHierarchy::RefreshGraphs)
            ]
            + SHorizontalBox::Slot().AutoWidth().Padding(8, 2)
            [
                SNew(SCheckBox)
                .IsChecked(this, &SLandscapeSplineHierarchy::GetAlwaysVisibleState)
                .OnCheckStateChanged_Lambda([this](ECheckBoxState) { ToggleAlwaysVisible(); })
                [SNew(STextBlock).Text(NSLOCTEXT("LandscapeSplineHierarchy", "AlwaysVisible", "Always Visible Splines"))]
            ]
        ]
        + SVerticalBox::Slot().AutoHeight().Padding(6, 2)
        [
            SNew(STextBlock)
            .Text(NSLOCTEXT("LandscapeSplineHierarchy", "Help", "Each row is one disconnected native Landscape Spline network. Select works independently of the camera angle."))
            .AutoWrapText(true)
        ]
        + SVerticalBox::Slot().AutoHeight().Padding(4)[SNew(SSeparator)]
        + SVerticalBox::Slot().FillHeight(1).Padding(4)
        [
            SNew(SScrollBox) + SScrollBox::Slot()[SAssignNew(GroupBox, SVerticalBox)]
        ]
    ];
    Refresh();
}

void SLandscapeSplineHierarchy::Refresh()
{
    if (!GroupBox) return;
    GroupBox->ClearChildren();
    FLandscapeSplineHierarchyService& Service = FLandscapeSplineHierarchyService::Get();
    ALandscape* Landscape = Service.FindCurrentLandscape();
    ALandscapeSplineHierarchyMetadata* Metadata = Service.SynchronizeAutomaticSplineGraphs(Landscape);
    if (!Metadata || Metadata->Groups.IsEmpty())
    {
        GroupBox->AddSlot().AutoHeight().Padding(4)
        [SNew(STextBlock).Text(NSLOCTEXT("LandscapeSplineHierarchy", "NoSplines", "Select the Landscape or one spline point, then refresh."))];
        return;
    }
    for (const FLandscapeSplineGroup& Group : Metadata->Groups)
    {
        GroupBox->AddSlot().AutoHeight().Padding(0, 2)[BuildGroupRow(Metadata, Group.Id)];
    }
}

TSharedRef<SWidget> SLandscapeSplineHierarchy::BuildGroupRow(ALandscapeSplineHierarchyMetadata* Metadata, const FGuid& GroupId)
{
    const FLandscapeSplineGroup* Group = Metadata->Groups.FindByPredicate([&](const FLandscapeSplineGroup& Item) { return Item.Id == GroupId; });
    const int32 NumPoints = Group ? Group->ControlPoints.Num() : 0;
    const int32 NumSegments = Group ? Group->Segments.Num() : 0;
    const FText Summary = FText::Format(NSLOCTEXT("LandscapeSplineHierarchy", "Summary", "{0} points  |  {1} segments"), FText::AsNumber(NumPoints), FText::AsNumber(NumSegments));

    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
        .Padding(5)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1).Padding(2)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [
                    SNew(SEditableTextBox)
                    .Text_Lambda([Metadata, GroupId]
                    {
                        const FLandscapeSplineGroup* Item = Metadata->Groups.FindByPredicate([&](const FLandscapeSplineGroup& G) { return G.Id == GroupId; });
                        return Item ? FText::FromName(Item->Name) : FText::GetEmpty();
                    })
                    .OnTextCommitted_Lambda([Metadata, GroupId](const FText& Text, ETextCommit::Type)
                    {
                        if (FLandscapeSplineGroup* Item = Metadata->Groups.FindByPredicate([&](const FLandscapeSplineGroup& G) { return G.Id == GroupId; }))
                        {
                            Metadata->Modify();
                            Item->Name = FName(*Text.ToString());
                            Metadata->MarkPackageDirty();
                        }
                    })
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(2, 1)
                [SNew(STextBlock).Text(Summary).ColorAndOpacity(FSlateColor::UseSubduedForeground())]
            ]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(4)
            [
                SNew(SButton)
                .Text(NSLOCTEXT("LandscapeSplineHierarchy", "SelectSpline", "Select"))
                .ToolTipText(NSLOCTEXT("LandscapeSplineHierarchy", "SelectSplineTip", "Select all control points and segments in this spline network."))
                .OnClicked_Lambda([Metadata, GroupId]
                {
                    FLandscapeSplineHierarchyService::Get().SelectGroup(Metadata, GroupId);
                    return FReply::Handled();
                })
            ]
        ];
}

FReply SLandscapeSplineHierarchy::RefreshGraphs()
{
    Refresh();
    return FReply::Handled();
}

FReply SLandscapeSplineHierarchy::ToggleAlwaysVisible()
{
    FLandscapeSplineHierarchyService& Service = FLandscapeSplineHierarchyService::Get();
    Service.SetAlwaysVisibleEnabled(!Service.IsAlwaysVisibleEnabled());
    return FReply::Handled();
}

ECheckBoxState SLandscapeSplineHierarchy::GetAlwaysVisibleState() const
{
    return FLandscapeSplineHierarchyService::Get().IsAlwaysVisibleEnabled() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
}

FText SLandscapeSplineHierarchy::GetStatusText() const
{
    return FText::GetEmpty();
}
