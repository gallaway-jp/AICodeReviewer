# Milestone 2 Review Definitions Handoff

Date: 2026-04-04

## Objective

Start Milestone 2 from the platform extensibility roadmap: custom review types and subtype-aware review definitions.

This first slice stays narrow. It does not add review-pack loading or new GUI subtype controls yet. It hardens the existing review registry so later custom-definition work has a stable canonicalization and metadata boundary.

## Strict Audit Of Remaining Direct App-Internal Reads

The remaining direct app-internal reads in GUI-adjacent tests were re-audited before starting Milestone 2.

Classification:

- intentional low-level smoke/runtime setup seams
- intentional lower-level scheduler or facade monkeypatch seams in workflow tests
- intentional direct widget or state setup in settings and session tests
- intentional harness-owned bridging reads inside `tests/gui_test_utils.py`

Conclusion:

- there were no remaining broad GUI-facing state-observation leaks worth another Milestone 1 cleanup slice
- Milestone 1 is at a practical stop point

## Completed In This Slice

- enriched `ReviewDefinition` in `src/aicodereviewer/registries/review_registry.py` with:
  - `parent_key`
  - `aliases`
  - `requires_spec_content`
- extended `ReviewRegistry` with:
  - alias registration and collision checks
  - `resolve_key(...)`
  - `resolve(...)`
  - `list_children(...)`
- added built-in review metadata wiring in `src/aicodereviewer/backends/base.py` for:
  - review aliases
  - subtype parent mapping
  - spec-content requirements
- updated CLI review-type parsing in `src/aicodereviewer/main.py` to:
  - expand `all` from registry-visible keys
  - resolve aliases through the registry
  - deduplicate alias and canonical mixes to canonical keys
  - keep preset expansion behavior intact
- updated execution validation and runtime normalization in `src/aicodereviewer/execution/service.py` to:
  - canonicalize review types at the execution boundary
  - validate unknown types through registry resolution
  - enforce spec-content requirements from definition metadata instead of hard-coded type checks
- added focused tests covering:
  - registry alias resolution
  - subtype parent metadata for `architectural_review`
  - CLI alias parsing for `spec` and `i18n`
  - execution-side alias normalization and spec validation

## Follow-On Slice: Extracted Definitions, Custom Packs, And Subtype-Aware Surfaces

Completed in this follow-on slice:

- moved built-in review definition data out of `src/aicodereviewer/backends/base.py` into a dedicated `src/aicodereviewer/review_definitions.py` module
- kept the current public registry-facing API stable by continuing to expose:
  - `REVIEW_PROMPTS`
  - `REVIEW_TYPE_META`
  - `REVIEW_TYPE_KEYS`
  - `get_review_registry()`
- added review-pack discovery and composition in `src/aicodereviewer/review_definitions.py`:
  - built-ins are always registered first
  - custom packs load from `review_packs/*.json` relative to the active config directory
  - additional pack paths can be configured through `[review_packs] paths` in `config.ini`
  - explicit empty pack lists now mean built-ins only
- added pack validation and explicit diagnostics for:
  - invalid JSON
  - unsupported pack version
  - malformed review-definition payloads
  - unknown or cyclic parent relationships
  - duplicate keys or aliases through registry registration checks
- added parent-aware inheritance for user-defined subtype packs:
  - omitted `label`, `group`, `summary_key`, and `requires_spec_content` inherit from the parent definition
  - omitted `prompt` inherits the parent prompt
  - `prompt_append` extends the inherited or explicit prompt without requiring callers to duplicate the parent prompt text
- extended `ReviewRegistry` with:
  - `lineage_keys(...)`
  - `iter_hierarchy(...)`
- made backend prompt assembly subtype-aware so parent review rules still apply when a subtype is selected
- updated CLI help output to render subtype hierarchy from the live registry instead of only from a flat static key list
- updated the Review tab to render review-type checkboxes from the live registry hierarchy instead of `REVIEW_TYPE_KEYS`, including visible child indentation and subtype marker text
- added a minimal custom review-pack example at `examples/review-pack-secure-defaults.json`

## Validation

Focused validation for this slice:

- `tests/test_backends.py tests/test_main_cli.py tests/test_execution_service.py` -> `80 passed`
- `tests/test_architectural_review.py tests/test_interaction_analysis.py` -> `72 passed`

Focused validation for the extraction and custom-pack follow-on slice:

- `tests/test_review_definitions.py tests/test_backends.py tests/test_main_cli.py tests/test_execution_service.py tests/test_framework_prompt.py tests/test_gui_smoke.py` -> `197 passed`
- `tests/test_gui_workflows.py -k "review_type_preset_picker or save_and_restore_review_form_values"` -> `1 passed`
- `tests/test_architectural_review.py tests/test_interaction_analysis.py` -> `72 passed`

## Current Milestone 2 Position

The codebase now has the minimal registry semantics needed for later Milestone 2 slices:

- canonical review keys
- alias resolution
- parent-child review metadata
- definition-owned validation flags
- dedicated built-in definition storage outside `backends/base.py`
- built-in plus user-defined review-pack composition
- subtype-aware CLI help rendering and GUI review-type selection

What is still intentionally deferred:

- deeper roadmap schema fields that still have no downstream consumers yet beyond storage and prompt/matching hooks

## Follow-On Slice: Dynamic Presets, Invocation-Scoped Packs, And Richer Pack Metadata

Completed in this slice:

- extended `ReviewDefinition` metadata with:
  - `category_aliases`
  - `context_augmentation_rules`
  - `benchmark_metadata`
- extended pack parsing in `src/aicodereviewer/review_definitions.py` so review packs can now define:
  - richer subtype metadata fields above
  - custom `review_presets` payloads validated against the live registry
- kept preset callers stable by preserving `REVIEW_TYPE_PRESETS` while moving preset composition into `src/aicodereviewer/review_presets.py`
- added preset validation and canonicalization behavior so preset bundles can reference custom subtype keys and registry aliases without duplicating canonical names manually
- updated registry installation to install both review definitions and review presets together as one composed pack state
- added per-invocation CLI pack injection through `--review-pack`, including pre-parse installation so the same invocation's help text, preset listing, and `--type` parsing all see injected pack content
- updated backend prompt building to append inherited `context_augmentation_rules` from the selected subtype lineage
- updated downstream issue-type normalization and benchmark matching to honor registry-backed `category_aliases` in addition to the existing hard-coded aliases
- expanded the example pack at `examples/review-pack-secure-defaults.json` to show:
  - custom subtype metadata
  - custom benchmark metadata
  - a custom `secure_runtime` review preset

Focused validation for this slice:

- `tests/test_review_definitions.py tests/test_main_cli.py tests/test_backends.py tests/test_gui_smoke.py` -> `82 passed`
- `tests/test_gui_workflows.py -k "review_type_preset_picker"` -> `1 passed`

## Recommended Next Slice

Continue Milestone 2 by widening preset support and pack schema depth on top of the now-stable registry layer.

The highest-leverage next step is:

- start consuming `benchmark_metadata` in the benchmark runner and artifact generation path instead of only storing it on definitions
- decide whether review-pack presets also need preset aliases or pack-level grouping metadata before broader authoring UX work

## Follow-On Slice: Benchmark Metadata Consumption And Preset Authoring Contract

Completed in this slice:

- started consuming review-definition `benchmark_metadata` in `src/aicodereviewer/benchmarking.py` by:
  - attaching aggregated benchmark metadata to per-fixture evaluation results
  - carrying the same metadata into benchmark invocation descriptions
  - surfacing run-level aggregated metadata in the machine-readable benchmark summary
- exposed `benchmark_metadata` in the existing benchmark presentation surfaces that already act as fixture-selection or comparison UIs:
  - `benchmarking.py --list-fixtures` now emits fixture tags and focus areas when present
  - `tools/run_review_type_degradation_study.py` now preserves representative fixture metadata and per-run benchmark metadata in its summary payload
  - `tools/run_review_type_pairwise_interference.py` now preserves representative fixture metadata and per-run benchmark metadata in its summary payload
- updated `tools/run_holistic_benchmarks.py` so generated benchmark report records now preserve:
  - invocation scope
  - invocation review types
  - invocation benchmark metadata
- decided that custom review-pack presets should keep alias support now because it is low-risk, already fits the existing canonicalization model, and improves CLI authoring ergonomics without changing UI structure
- added preset grouping metadata to the existing preset presentation surfaces because those UI and CLI consumers now exist:
  - `src/aicodereviewer/review_presets.py` supports optional preset `group`
  - CLI preset listings now show group labels alongside preset names
  - the GUI review-tab preset picker now renders grouped preset labels
- updated the example pack to demonstrate a custom preset alias and custom preset group for `secure_runtime`

Focused validation for this slice:

- `tests/test_benchmarking.py tests/test_main_cli.py tests/test_run_review_type_degradation_study.py tests/test_run_review_type_pairwise_interference.py` -> `187 passed`
- `tests/test_gui_smoke.py::TestAppCreation::test_review_tab_renders_custom_subtype_hierarchy` -> `1 passed`
- `tests/test_gui_workflows.py::test_review_type_preset_picker_applies_bundle_and_tracks_exact_match` -> `1 passed`

## Recommended Next Slice

Continue Milestone 2 by widening preset authoring UX on top of the now-stable registry and benchmark metadata contract.

The highest-leverage next step is:

- expose benchmark metadata in any future desktop benchmark surface if a dedicated in-app benchmark browser or comparison view is added
- keep preset grouping metadata stable and only broaden it further if a richer grouped-picker UI needs ordering, collapsing, or section descriptions

## Follow-On Slice: Dedicated In-App Benchmark Browser

Completed in this slice:

- added a dedicated Benchmarks tab to `src/aicodereviewer/gui/app.py` through a new `src/aicodereviewer/gui/benchmark_mixin.py` mixin instead of introducing a one-off popup flow
- kept the desktop benchmark browser aligned with the existing benchmark payload contract by supporting two sources:
  - direct fixture discovery from a fixtures root using `discover_fixtures(...)` and `describe_fixture_catalog_entry(...)`
  - summary-artifact loading from `representative_fixtures` entries that already carry `benchmark_metadata`
- rendered benchmark metadata in-app for both sources, including:
  - fixture tags
  - expected focus areas
  - per-review-type registry metadata when present in the loaded payload
- added benchmark-tab localisation in both English and Japanese
- added focused GUI coverage for:
  - benchmark-tab widget creation and testing-mode browse no-ops
  - fixture-catalog loading into the tab browser
  - representative-fixture summary-artifact loading into the tab browser

Focused validation for this slice:

- `tests/test_gui_smoke.py tests/test_i18n.py` -> `82 passed`
- `tests/test_gui_workflows.py::test_benchmark_tab_loads_representative_fixture_summary_artifact` -> `1 passed`

## Recommended Next Slice

Continue Milestone 2 by expanding benchmark-browser utility only where there is an immediate user flow.

The highest-leverage next step is:

- add optional actions on the Benchmarks tab only if they reuse existing benchmark tooling cleanly, such as opening fixture folders or loading generated summary JSON for comparison
- keep preset grouping unchanged unless a future grouped picker needs ordering or descriptive sections beyond the current label decoration

## Follow-On Slice: Benchmark Tab Actions And Summary Selector

Completed in this slice:

- extended the Benchmarks tab so users can open the currently loaded benchmark source directly from the UI:
  - when browsing a live fixture catalog, the action opens the selected fixture's project folder when available
  - when browsing a summary artifact, the action opens the summary artifact directory
- added a small benchmark-summary selector backed by an artifacts root scan:
  - the tab now discovers benchmark-like JSON artifacts under the configured artifacts directory
  - users can load a selected summary directly into the primary fixture browser without using a file dialog
- added a lightweight side-by-side comparison lane for a second summary artifact:
  - the primary fixture browser still consumes `representative_fixtures`
  - a second summary artifact can now be loaded separately for summary-level comparison without disturbing the primary selection browser
  - the comparison view shows overview metrics such as backend, status, overall score, representative fixture count, and representative fixture-id overlap/delta versus the primary summary when available
- kept the new actions aligned with the existing benchmark payload contract instead of introducing a second benchmark model

Focused validation for this slice:

- `tests/test_gui_smoke.py -k "benchmark_tab" tests/test_gui_workflows.py -k "benchmark_tab" tests/test_i18n.py` -> `5 passed`
- `tests/test_gui_smoke.py tests/test_i18n.py tests/test_gui_workflows.py -k "benchmark_tab or test_key_exists_in_en or test_key_exists_in_ja or TestAppCreation or TestTestingMode"` -> `63 passed`

## Recommended Next Slice

Continue Milestone 2 by keeping the benchmark UI thin and artifact-driven.

The highest-leverage next step is:

- add richer comparison only if users need fixture-level diffs between two summary artifacts, reusing `representative_fixtures` instead of inventing a separate compare schema
- keep the artifact selector scoped to benchmark-style JSON outputs unless there is a real need to browse arbitrary review reports from the Benchmarks tab

## Follow-On Slice: Fixture-Level Compare And Triage Shortcuts

Completed in this slice:

- extended the benchmark comparison lane beyond overview metrics by adding fixture-level diffing derived from the existing summary payload:
  - shared fixture ids now show per-fixture score deltas when score data is present
  - shared fixture ids now show status changes when the two summaries disagree
  - shared fixture ids now show review-type additions and removals when the selected review bundle changed across runs
- kept fixture-level comparison artifact-driven by merging information from existing fields such as:
  - `representative_fixtures`
  - `score_summary.results`
  - `baseline_results`
  - `pair_results`
  - `generated_reports`
- added quick-open actions for benchmark triage directly from the Benchmarks tab:
  - open the selected benchmark summary JSON
  - open the generated reports directory inferred from the selected summary's `generated_reports` entries
- kept these actions selector-driven first, with fallback to the currently loaded primary summary when needed

Focused validation for this slice:

- `tests/test_gui_smoke.py -k "benchmark_tab" tests/test_gui_workflows.py -k "benchmark_tab" tests/test_i18n.py` -> `6 passed`
- `tests/test_gui_smoke.py tests/test_i18n.py tests/test_gui_workflows.py -k "benchmark_tab or test_key_exists_in_en or test_key_exists_in_ja or TestAppCreation or TestTestingMode"` -> `64 passed`

## Recommended Next Slice

Continue Milestone 2 by only deepening benchmark comparison where there is a clear triage need.

The highest-leverage next step is:

- add report-level drill-in from fixture-level compare rows only if users need to jump directly from a changed fixture to the two underlying generated report JSON files
- keep the compare lane summary-driven unless a later workflow proves that full report diff visualization belongs inside the desktop app

## Follow-On Slice: Compact Fixture Diff Table And Row-Level Report Open Actions

Completed in this slice:

- added a compact fixture diff table widget to the Benchmarks tab compare lane so changed fixtures are easier to scan than in the narrative comparison text alone
- the new table is driven by the same fixture-delta records already derived from the summary payload and renders compact columns for:
  - fixture id
  - primary score/status
  - comparison score/status
  - score delta
  - review-type delta summary
- added direct row-level open actions for the two report JSON files involved in a changed fixture row:
  - open primary report JSON
  - open comparison report JSON
- kept report-path resolution artifact-driven by reusing existing summary fields such as `report_path` and `output_path`, resolved relative to the summary artifact when necessary

Focused validation for this slice:

- `tests/test_gui_smoke.py -k "benchmark_tab" tests/test_gui_workflows.py -k "benchmark_tab" tests/test_i18n.py` -> `7 passed`
- `tests/test_gui_smoke.py tests/test_i18n.py tests/test_gui_workflows.py -k "benchmark_tab or test_key_exists_in_en or test_key_exists_in_ja or TestAppCreation or TestTestingMode"` -> `65 passed`

## Recommended Next Slice

Continue Milestone 2 by resisting report-level UI sprawl unless users clearly need it.

The highest-leverage next step is:

- add per-row open actions for diffing or previewing the two underlying report payloads only if plain JSON open is not enough for benchmark triage
- keep the compact table focused on changed shared fixtures unless a later workflow proves that compare-only or primary-only fixtures need their own row treatment

## Follow-On Slice: Inline Report Preview/Diff And Presence-Aware Fixture Rows

Completed in this slice:

- expanded the compact fixture diff table so it no longer covers only changed shared fixtures:
  - shared changed fixtures still render as before
  - primary-only fixtures now get dedicated rows
  - comparison-only fixtures now get dedicated rows
- added an explicit presence column to the compact diff table so triage can distinguish shared, primary-only, and comparison-only rows at a glance
- added inline report drill-in below the table instead of forcing every triage action to leave the app:
  - per-row preview action now renders the primary and comparison report JSON payloads side by side when available
  - per-row diff action now renders a unified textual diff between the two preview payloads
  - missing report payloads are surfaced inline with localized empty-state text rather than silently reusing stale preview content
- kept the preview/diff surface artifact-driven by reusing the existing summary-relative report-path resolution and current row record model instead of introducing a separate report viewer contract

Focused validation for this slice:

- `tests/test_gui_workflows.py::test_benchmark_tab_loads_representative_fixture_summary_artifact tests/test_gui_workflows.py::test_benchmark_tab_opens_fixture_diff_report_json_files tests/test_gui_workflows.py::test_benchmark_tab_previews_and_diffs_fixture_reports tests/test_gui_smoke.py::TestAppCreation::test_benchmark_tab_widgets tests/test_i18n.py` -> `59 passed`

## Recommended Next Slice

Continue Milestone 2 by only deepening benchmark triage where there is a clear workflow need.

The highest-leverage next step is:

- add filtering or row selection affordances only if the expanded table becomes dense enough that presence-state rows need separate views
- keep report diffing textual unless users demonstrate a need for semantic issue-level diff grouping inside the desktop app

## Follow-On Slice: Presence-State Filtering And Broader Benchmark Regression

Completed in this slice:

- added a localized presence-state filter to the Benchmarks tab compact fixture diff table so users can switch between:
  - all fixture rows
  - shared rows only
  - primary-only rows only
  - comparison-only rows only
- kept filtering layered on top of the existing fixture diff record model instead of introducing a second compare representation:
  - `_build_fixture_diff_records(...)` still owns the canonical row list
  - `_render_fixture_diff_table(...)` now reapplies the selected presence filter when rows refresh
- added a localized empty state for filters that produce no visible rows while preserving the existing empty state for the no-comparison-loaded case
- extended the GUI benchmark harness so workflow tests can drive the new filter control directly
- broader GUI workflow regression also exposed that shared results-tab filter helpers were attached only to the benchmark harness in `tests/gui_test_utils.py`; that seam was corrected so the broader file-level regression slice passes again

Focused validation for this slice:

- `tests/test_gui_workflows.py::test_benchmark_tab_filters_fixture_diff_rows_by_presence tests/test_gui_smoke.py::TestAppCreation::test_benchmark_tab_widgets tests/test_i18n.py` -> covered within broader pass below

Broader validation for this slice:

- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_i18n.py` -> `151 passed`

## Recommended Next Slice

Continue Milestone 2 by sharpening benchmark triage only where the current artifact-driven surface still feels slow.

The highest-leverage next step is:

- add row sorting only if users need to prioritize the filtered table by score delta, status change, or review-type churn
- keep the presence filter simple unless repeated workflows show a need for multi-select or persisted benchmark-tab view state

## Follow-On Slice: Benchmark Row Sorting And Milestone 2 Exit Check

Completed in this slice:

- added a localized sort control beside the existing presence filter on the Benchmarks tab compact fixture diff table
- kept sorting layered on top of the existing diff-row record list rather than introducing another benchmark compare representation
- added three table sort modes for the current triage workflow:
  - default order
  - largest score delta
  - status churn first
- preserved the current artifact-driven row contract by attaching sort metadata to the existing row records:
  - numeric score-delta values stay on shared rows when present
  - status-change flags stay on shared rows when the two summaries disagree
  - presence rank still anchors default ordering and tie-breaking for non-shared rows
- extended the GUI benchmark harness so workflow tests can drive the sort control directly and assert sorted row order under the existing presence filter
- rechecked the remaining benchmark-expansion notes before proposing Milestone 3 work:
  - `holistic-open-gaps.md` no longer tracks unresolved benchmark-expansion blockers
  - the remaining benchmark-tab work is now optional polish rather than a Milestone 2 blocker

Broader validation for this slice:

- `tests/test_gui_smoke.py tests/test_gui_workflows.py tests/test_i18n.py` -> `152 passed`

## Recommended Next Slice

Milestone 2 is now at a practical stopping point unless there is a new benchmark-triage workflow to optimize.

The previously deferred benchmark polish items have now been narrowed further:

- benchmark filter and sort preferences now persist through the existing GUI config, with comparison-specific view state keyed by the current primary/comparison summary pair and restored when that same pair is revisited
- inline report diffing now prepends an issue-level semantic summary derived from structured `issues_found` / `issues` payloads before the raw unified JSON diff, which makes severity and issue-presence churn easier to scan
- broader validation for this follow-on refinement slice: `tests/test_gui_workflows.py tests/test_gui_smoke.py tests/test_i18n.py` -> `153 passed`
- the remaining optional benchmark-browser polish is limited to richer multi-select or secondary sort modes if real usage shows the current single-select controls are insufficient

If none of those workflow pressures exist, the next milestone can start from the current benchmark browser state without another Milestone 2 benchmark slice.
