# DP Unreal Context Export

Read-only foundation for stable, machine-readable Unreal asset context. It does not save assets, load maps, compile graphs, or change editor state.

## First run

Run `export_context.py` through Unreal Python and pass a JSON config path as the first argument. The config contains an explicit asset allowlist and an output root. The exporter creates one JSON document per asset plus `assets-index.json`.

For PCG, prefer Epic's official MCP `GetGraphStructure` result and normalize it with `ingest_mcp_pcg.py`. It already exposes nodes, positions, edges, parameters, descriptions, and comments without custom reflection.

For Blueprints, collect `list_graphs` plus `read_graph_dsl` and normalize them with `ingest_mcp_blueprint.py`. The original DSL and a deterministic S-expression AST are retained. Node positions are explicitly marked unavailable rather than guessed.

For Materials and MaterialFunctions, batch the official `MaterialTools` and `ObjectTools` reads, then normalize with `ingest_mcp_material.py`. Only selected documented properties are exported; unavailable comment-box coverage remains explicit.

Validate an export outside Unreal with:

`python tools/unreal_context_export/validate_export.py context/unreal`

Generate the combined structural and readability report with:

`python tools/unreal_context_export/run_checks.py context/unreal`

Evaluate a graph-change evidence bundle without treating omitted checks as success:

`python tools/unreal_context_export/acceptance_gate.py evidence.json acceptance.json`

Validate an append-only action log with:

`python tools/unreal_context_export/validate_action_log.py context/unreal/actions/2026-11-17.jsonl`

Compare two export snapshots semantically with:

`python tools/unreal_context_export/diff_exports.py before/context/unreal after/context/unreal diff.json`

The diff identifies changed assets, nodes, links, and dependencies. It is the future bridge for concise change summaries; it does not update Notion or Jira by itself.

Run the complete local verification loop with Unreal 5.8's bundled Python:

`Engine/Binaries/ThirdParty/Python3/Win64/python.exe tools/unreal_context_export/verify_pipeline.py`

This reruns all unit tests, compiles the Python modules, validates every export and action log, evaluates the acceptance evidence, and writes `context/unreal/validation/pipeline.json`. A `partial` result is intentional while engine-side compile/Data Validation evidence is absent.

Run the pure-Python tests with:

`python -m unittest discover tools/unreal_context_export/tests`

## Guarantees

- Stable schema identifier: `dp.unreal.context/v1`
- Explicit coverage flags; unsupported graph details are never presented as complete
- Per-asset errors instead of aborting the whole export
- Dependencies and referencers are recorded
- Material node positions, pins, and input links are exported through UE 5.8's official `MaterialEditingLibrary` APIs
- `layout_audit.py` reports long wires and high fan-out conservatively; it never rearranges a graph
- No asset save, map load, compile, source-control, or editor-global operation

Material comment coverage, Blueprint pin/link topology, and PCG node topology are intentionally reported as incomplete until their UE 5.8 APIs have been verified against the installed engine. Native `DPAutomation` getters should be added only for facts Unreal Python cannot expose reliably.
