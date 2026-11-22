#include "DPAutomationLibrary.h"
#include "PCGGraph.h"
#include "HierarchyEditor/PropertyBagHierarchyViewModel.h"
#include "ScopedTransaction.h"


namespace
{
FString ExtendOpenAreaLayout(UPCGGraph& Graph, UPropertyBagHierarchyRoot& Root, const UPropertyBag& Bag)
{
    const TPair<FName, FName> Destinations[] = {
        {TEXT("Bodendetails_Assets"), TEXT("Bodendetails")},
        {TEXT("Kleine_Buesche_Assets"), TEXT("Kleine Buesche")},
        {TEXT("Deckungsbuesche_Assets"), TEXT("Deckungsbuesche")},
        {TEXT("Wildgras_Assets"), TEXT("Wildgras")},
        {TEXT("Begleitgras_Aktiv"), TEXT("Begleitgras")},
        {TEXT("Begleitgras_Radius_cm"), TEXT("Begleitgras")},
        {TEXT("Begleitgras_Dichte_pro_m2"), TEXT("Begleitgras")}
    };

    TArray<UPropertyBagHierarchyCategory*> Categories;
    TArray<UPropertyBagHierarchyProperty*> Properties;
    Root.GetChildrenOfType(Categories, false);
    Root.GetChildrenOfType(Properties, true);

    struct FMove
    {
        const FPropertyBagPropertyDesc* Desc;
        FName Category;
        UPropertyBagHierarchyProperty* Item;
    };
    TArray<FMove> Moves;
    for (const auto& [Name, Category] : Destinations)
    {
        const FPropertyBagPropertyDesc* Desc = Bag.FindPropertyDescByName(Name);
        if (!Desc)
        {
            continue;
        }

        const FHierarchyElementIdentity Identity({Desc->ID}, {});
        auto* const Found = Properties.FindByPredicate([&](const UPropertyBagHierarchyProperty* Item)
        {
            return Item->GetPersistentIdentity() == Identity;
        });
        UPropertyBagHierarchyProperty* Item = Found ? *Found : nullptr;
        const UPropertyBagHierarchyCategory* Parent = Item ? Cast<UPropertyBagHierarchyCategory>(Item->GetOuter()) : nullptr;
        if (!Parent || Parent->GetOuter() != &Root || Parent->GetCategoryName() != Category)
        {
            Moves.Add({Desc, Category, Item});
        }
    }

    if (Moves.IsEmpty())
    {
        return TEXT("OpenArea parameter hierarchy already up to date");
    }

    const FScopedTransaction Transaction(NSLOCTEXT("DP", "ExtendOpenAreaParameterLayout", "Group new OpenArea parameters"));
    Graph.Modify();
    Root.Modify();
    for (const FMove& Move : Moves)
    {
        auto* const Found = Categories.FindByPredicate([&](const UPropertyBagHierarchyCategory* Category)
        {
            return Category->GetCategoryName() == Move.Category;
        });
        UPropertyBagHierarchyCategory* Destination = Found ? *Found : nullptr;
        if (!Destination)
        {
            Destination = NewObject<UPropertyBagHierarchyCategory>(&Root, NAME_None, RF_Transactional);
            Destination->SetCategoryName(Move.Category);
            Destination->SetIdentity(FHierarchyElementIdentity({FGuid::NewGuid()}, {}));
            Root.GetChildrenMutable().Add(Destination);
            Categories.Add(Destination);
        }

        Destination->Modify();
        if (UPropertyBagHierarchyProperty* Item = Move.Item)
        {
            UHierarchyElement* Parent = CastChecked<UHierarchyElement>(Item->GetOuter());
            Parent->Modify();
            Item->Modify();
            const FName UniqueName = MakeUniqueObjectName(Destination, Item->GetClass(), Item->GetFName());
            if (!Item->Rename(*UniqueName.ToString(), Destination, REN_DontCreateRedirectors))
            {
                return FString::Printf(TEXT("ERROR: Could not move OpenArea parameter %s"), *Move.Desc->Name.ToString());
            }
            Parent->GetChildrenMutable().Remove(Item);
            Destination->GetChildrenMutable().Add(Item);
        }
        else
        {
            UPropertyBagHierarchyProperty* NewItem = NewObject<UPropertyBagHierarchyProperty>(Destination, NAME_None, RF_Transactional);
            NewItem->SetIdentity(FHierarchyElementIdentity({Move.Desc->ID}, {}));
            Destination->GetChildrenMutable().Add(NewItem);
        }
    }

    Root.OnHierarchyModified.Broadcast();
    Graph.MarkPackageDirty();
    return FString::Printf(TEXT("Grouped %d new OpenArea parameters into existing layout; unsaved"), Moves.Num());
}
}
FString UDPAutomationLibrary::OrganizeOpenAreaParameters()
{
    UPCGGraph* Graph = LoadObject<UPCGGraph>(nullptr, TEXT("/Game/DP/PCG/Graphs/PCG_OpenArea.PCG_OpenArea"));
    if (!Graph) return TEXT("ERROR: OpenArea graph not found");
    UPropertyBagHierarchyRoot* Root = Cast<UPropertyBagHierarchyRoot>(Graph->GetUserParameterHierarchyRoot());
    const FInstancedPropertyBag* Bag = Graph->GetUserParametersStruct();
    if (!Root || !Bag || !Bag->GetPropertyBagStruct()) return TEXT("ERROR: Native parameter hierarchy unavailable");

    // Extend an authored layout in place. Unrelated categories and items retain their identities.
    for (const auto& Child : Root->GetChildren())
        if (!Cast<UPropertyBagHierarchyProperty>(Child)) return ExtendOpenAreaLayout(*Graph, *Root, *Bag->GetPropertyBagStruct());

    const TArray<FName> Categories = {TEXT("Hauptgras"), TEXT("Randfuellung"), TEXT("Bodendetails"),
        TEXT("Kleine Buesche"), TEXT("Deckungsbuesche"), TEXT("Wildgras"), TEXT("Diagnose"), TEXT("Weitere"), TEXT("Begleitgras")};
    auto CategoryFor = [](const FName Name) -> int32
    {
        const FString S = Name.ToString();
        if (S == TEXT("Hauptgras_Mesh") || S == TEXT("Basisdichte_pro_m2")) return 0;
        if (S.StartsWith(TEXT("Rand")) || S == TEXT("Fuellabstand_cm") || S == TEXT("Kleinbueschel_Steinabstand_cm")) return 1;
        if (S.StartsWith(TEXT("Bodendetails_"))) return 2;
        if (S.StartsWith(TEXT("Kleine_Buesche_"))) return 3;
        if (S.StartsWith(TEXT("Deckungsbuesche_"))) return 4;
        if (S.StartsWith(TEXT("Wildgras_")) || S == TEXT("Verwilderung_Stufe")) return 5;
        if (S.StartsWith(TEXT("Debug_"))) return 6;
        if (S.StartsWith(TEXT("Begleitgras_"))) return 8;
        return 7;
    };
    const FScopedTransaction Transaction(NSLOCTEXT("DP", "PCGParameterLayout", "Group OpenArea parameters"));
    Graph->Modify();
    Root->Modify();
    const auto OldChildren = Root->GetChildrenMutable();
    Root->GetChildrenMutable().Reset();
    TMap<int32, UPropertyBagHierarchyCategory*> Groups;
    int32 Count = 0;
    for (const FPropertyBagPropertyDesc& Desc : Bag->GetPropertyBagStruct()->GetPropertyDescs())
    {
        const int32 Index = CategoryFor(Desc.Name);
        UPropertyBagHierarchyCategory*& Group = Groups.FindOrAdd(Index);
        if (!Group)
        {
            Group = NewObject<UPropertyBagHierarchyCategory>(Root, NAME_None, RF_Transactional);
            Group->SetCategoryName(Categories[Index]);
            Group->SetIdentity(FHierarchyElementIdentity({FGuid::NewGuid()}, {}));
        }
        const FHierarchyElementIdentity Identity({Desc.ID}, {});
        UPropertyBagHierarchyProperty* Item = nullptr;
        for (const auto& Child : OldChildren)
            if (Child->GetPersistentIdentity() == Identity) Item = Cast<UPropertyBagHierarchyProperty>(Child);
        if (Item)
        {
            Item->Modify();
            Item->Rename(nullptr, Group, REN_DontCreateRedirectors | REN_NonTransactional);
        }
        else
        {
            Item = NewObject<UPropertyBagHierarchyProperty>(Group, NAME_None, RF_Transactional);
            Item->SetIdentity(Identity);
        }
        Group->GetChildrenMutable().Add(Item);
        ++Count;
    }
    for (int32 Index = 0; Index < Categories.Num(); ++Index)
        if (UPropertyBagHierarchyCategory** Group = Groups.Find(Index)) Root->GetChildrenMutable().Add(*Group);
    Root->OnHierarchyModified.Broadcast();
    Graph->MarkPackageDirty();
    return FString::Printf(TEXT("Grouped %d existing parameters into %d native categories; values and IDs unchanged; unsaved"), Count, Groups.Num());
}

FString UDPAutomationLibrary::OrganizeNormalForestParameters()
{
    UPCGGraph* Graph = LoadObject<UPCGGraph>(nullptr, TEXT("/Game/DP/PCG/Graphs/PCG_Forest_Normal.PCG_Forest_Normal"));
    if (!Graph) return TEXT("ERROR: NormalForest graph not found");
    UPropertyBagHierarchyRoot* Root = Cast<UPropertyBagHierarchyRoot>(Graph->GetUserParameterHierarchyRoot());
    const FInstancedPropertyBag* Bag = Graph->GetUserParametersStruct();
    if (!Root || !Bag || !Bag->GetPropertyBagStruct()) return TEXT("ERROR: Native parameter hierarchy unavailable");

    TArray<UPropertyBagHierarchyProperty*> ExistingItems;
    TFunction<void(UHierarchyElement*)> Collect = [&](UHierarchyElement* Element)
    {
        if (auto* Property = Cast<UPropertyBagHierarchyProperty>(Element)) ExistingItems.Add(Property);
        for (const auto& Child : Element->GetChildren()) Collect(Child);
    };
    Collect(Root);

    const TArray<FName> Categories = {TEXT("Laubbaeume"), TEXT("Jungbaeume"), TEXT("Buschgruppen"), TEXT("Weitere")};
    auto CategoryFor = [](const FName Name) -> int32
    {
        const FString S = Name.ToString();
        if (S.StartsWith(TEXT("Baumgruppen_"))) return 0;
        if (S.StartsWith(TEXT("Jungbaeume_"))) return 1;
        if (S.StartsWith(TEXT("Buschgruppen_"))) return 2;
        return 3;
    };
    const FScopedTransaction Transaction(NSLOCTEXT("DP", "PCGParameterLayout", "Group NormalForest parameters"));
    Graph->Modify();
    Root->Modify();
    const auto OldChildren = ExistingItems;
    Root->GetChildrenMutable().Reset();
    TMap<int32, UPropertyBagHierarchyCategory*> Groups;
    int32 Count = 0;
    TArray<FPropertyBagPropertyDesc> Ordered;
    for (const auto& Desc : Bag->GetPropertyBagStruct()->GetPropertyDescs()) Ordered.Add(Desc);
    const TArray<FString> Suffixes = {TEXT("_Aktiv"),TEXT("_Assets"),TEXT("_Dichte"),TEXT("_GroesseMin"),TEXT("_GroesseMax"),TEXT("_Gruppenschwelle"),TEXT("_Abstandsradius"),TEXT("_Zufallsseed")};
    auto Rank = [&](FName Name) { for(int32 I=0; I<Suffixes.Num(); ++I) if(Name.ToString().EndsWith(Suffixes[I])) return I; return 99; };
    Ordered.StableSort([&](const auto& A, const auto& B) { return Rank(A.Name) < Rank(B.Name); });
    for (const FPropertyBagPropertyDesc& Desc : Ordered)
    {
        const int32 Index = CategoryFor(Desc.Name);
        UPropertyBagHierarchyCategory*& Group = Groups.FindOrAdd(Index);
        if (!Group)
        {
            Group = NewObject<UPropertyBagHierarchyCategory>(Root, NAME_None, RF_Transactional);
            Group->SetCategoryName(Categories[Index]);
            Group->SetIdentity(FHierarchyElementIdentity({FGuid::NewGuid()}, {}));
        }
        const FHierarchyElementIdentity Identity({Desc.ID}, {});
        UPropertyBagHierarchyProperty* Item = nullptr;
        for (const auto& Child : OldChildren)
            if (Child->GetPersistentIdentity() == Identity) Item = Cast<UPropertyBagHierarchyProperty>(Child);
        if (Item)
        {
            Item->Modify();
            Item->Rename(nullptr, Group, REN_DontCreateRedirectors | REN_NonTransactional);
        }
        else
        {
            Item = NewObject<UPropertyBagHierarchyProperty>(Group, NAME_None, RF_Transactional);
            Item->SetIdentity(Identity);
        }
        Group->GetChildrenMutable().Add(Item);
        ++Count;
    }
    for (int32 Index = 0; Index < Categories.Num(); ++Index)
        if (UPropertyBagHierarchyCategory** Group = Groups.Find(Index)) Root->GetChildrenMutable().Add(*Group);
    Root->OnHierarchyModified.Broadcast();
    Graph->MarkPackageDirty();
    return FString::Printf(TEXT("Grouped %d existing parameters into %d native categories; values and IDs unchanged; unsaved"), Count, Groups.Num());
}
