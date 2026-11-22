# DeltaPoly Unreal Tools

Versionierter Quellcode und technische Dokumentation fuer die Editor-Werkzeuge des DeltaPoly-Unreal-Projekts.

## Inhalt

- `unreal/python`: Editor-Python fuer Building, Districts, Vegetation und Worldbuilding.
- `unreal/plugins`: C++-Quellen ausgewaehlter Editor-Plugins. Generierte Builds sind ausgeschlossen.
- `tools/unreal_context_export`: Read-only-Exporter, Validatoren und kleine Regressionstests fuer strukturierte Unreal-Graphdaten.
- `docs`: stabile Architektur- und Pipelinebeschreibungen.

## Grenzen

Dieses Repository ist kein vollstaendiger Unreal-Projektklon. Es enthaelt keine `.uasset`-Dateien, Maps, Marketplace-Inhalte, Caches, Logs, Backups, Zugangsdaten oder persoenliche Live-Statusdateien. Der gespeicherte Unreal-Projektzustand bleibt die fachliche Ground Truth; JSON-Exporte dokumentieren nur ihre ausdruecklich angegebene Abdeckung.

## Pruefung

```powershell
python -m unittest discover -s tools/unreal_context_export/tests -p "test_*.py"
```

Graphify darf dieses Repository als Navigations- und Analyseindex verwenden. Es ist kein Writer fuer binaere Unreal-Assets.
