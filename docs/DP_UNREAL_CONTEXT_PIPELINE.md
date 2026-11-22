# DP Unreal Context- und Prüf-Pipeline

## Ziel

Codex erhält reproduzierbaren Kontext zu Blueprints, Materialien und PCG-Graphen, ohne jedes Asset erneut interaktiv abzufragen. Änderungen werden in einer nachvollziehbaren Prüfschleife behandelt: Export, Strukturprüfung, Compile/Data Validation, Referenzprüfung, gezielter Test und visueller Capture. Graph-Lesbarkeit ist Teil der Abnahme.

## Architektur

1. **Read-only Exporter:** explizite Asset-Allowlist, versionierte JSON-Dokumente, Abhängigkeiten, Referenzen, Datei-Hash und ehrliche Coverage-Angaben.
2. **Kontextablage:** `context/unreal/assets-index.json` und `context/unreal/graphs/*.json`. Graphify kann diese Textdateien später indizieren; die Pipeline hängt nicht von Graphify ab.
3. **Aktionsprotokoll:** append-only JSONL mit Operation, Assets, Status und Prüfnachweis. Keine unkontrollierten Vollprompts oder Geheimnisse protokollieren.
4. **Prüfschleife:** Dry Run → Änderung → Compile → Data Validation → Referenzprüfung → relevante Automation → API-seitiger Viewport-Capture → Ergebnisprotokoll.
5. **Backlog-Verknüpfung:** zunächst menschlich bestätigte Meilensteine in Notion. Später Git/Perforce-Revisionen und Jira/Notion-Tickets über stabile IDs verbinden; keine Statusänderung nur aus Dateibewegung ableiten.

## Graph-Lesbarkeit

Ein späterer Layout-Validator meldet, verändert aber zunächst nichts: sehr lange Verbindungen, hohe Fan-outs ohne Reroute, unkommentierte Funktionsbereiche, Überlappungen und nicht gruppierte öffentliche Parameter. Automatisches Arrangieren kommt erst nach Dry-Run-Diff und visueller Abnahme hinzu. Graphify ist dabei ein optionales Analyse-/Navigationswerkzeug, nicht der Writer.

## Phasen

- **Phase 1 – jetzt:** stabiles Schema, Allowlist-Exporter, Validator, Aktionslog, Tests. Material-Knotenpositionen; Blueprint/PCG nur mit expliziter Teilabdeckung.
- **Phase 2:** UE-5.8-Ground-Truth für Blueprint-Pins/Links, PCG-Knoten und Kommentare verifizieren; fehlende Fakten über kleine read-only `DPAutomation`-Getter ergänzen.
- **Phase 3:** Compile/Data-Validation/Referenz- und Capture-Runner mit einem Pilotasset; keine Map-Wechsel ohne globale Lease.
- **Phase 4:** inkrementelle Exporte nach Save/Commit, Source-Control-Revisionen und überprüfte Notion/Jira-Synchronisierung.
- **Phase 5:** geprüftes Batch-Migrationswerkzeug mit Dry Run, Allowlist, Sicherung, Diff, Wiederaufnahme und Rollback-Hinweis.

## Sicherheitsgrenzen

Der Exporter lädt keine Map, speichert keine Assets und löst keinen Build aus. Ein einzelnes binäres Unreal-Asset behält genau einen Writer. Automatischer Backlog-Abschluss erfolgt erst, wenn ein technischer Prüfnachweis und bei visuellen Aufgaben eine menschliche Abnahme vorliegen.

Ein Bericht darf nur `pass` melden, wenn Engine Data Validation tatsächlich belegt ist. Ohne diesen Nachweis lautet der Status `partial`, auch wenn Schema, Referenzen und Lesbarkeitsanalyse technisch fehlerfrei sind. Compile, Automation und visueller Capture werden zusätzlich als aufgabenspezifische Abnahmekriterien geführt und dürfen nicht aus einem reinen Exporttest abgeleitet werden.

Ausnahme: Ein nachweislich rein lesender Export darf Data Validation als `not_applicable` markieren, weil kein Assetzustand geändert wurde. Dies gilt ausschließlich für den Exportvorgang. Sobald ein Graph, Parameter, Asset oder Referenzpfad mutiert wird, ist `required=true` und ein fehlender Engine-Validierungsbeleg führt wieder zu `partial`.

### Automationsausführung

Epics nativer Automation Controller ist erreichbar und hat die relevanten PCG-, Blueprint- und Material-Toolsettests erfolgreich entdeckt. Die konkrete Auswahl steht in `tools/unreal_context_export/automation-plan.json`. Diese Tests werden im produktiven Editor nicht beiläufig ausgeführt: mehrere davon erstellen oder verändern eigene Testassets. Sie laufen erst mit globaler Editor-Lease oder in einer isolierten Projekt-/Editorinstanz. Reine Discovery ist bereits belegt; `not_run` bleibt bis zur tatsächlichen Ausführung sichtbar.
