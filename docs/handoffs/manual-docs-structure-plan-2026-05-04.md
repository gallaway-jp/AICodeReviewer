# Manual And Docs Structure Plan

## Why This Follow-Up Exists

The current docs set already covers the shipped product surfaces, but the task-oriented material is concentrated in a single large manual and the API/addon guides still mix walkthrough content with reference content.

That makes the next phase harder in three specific ways:

- image-heavy walkthroughs are awkward to maintain inside one long page
- step-by-step user tasks and contributor reference material bleed into each other
- addon authoring and local API usage do not yet have a clear tutorial path separate from their contract/reference pages

## Direction

Keep Markdown as the primary docs format.

Do not introduce a docs site generator in this phase.

Restructure the docs set into two complementary layers:

- root `docs/*.md` pages stay as durable reference and landing pages
- new `docs/guides/` pages become step-by-step, screenshot-friendly workflows

This keeps the current curated docs model intact while making room for richer walkthroughs, more images, and narrower pages that are easier to update when behavior changes.

## Proposed Information Architecture

### Keep As Top-Level Reference Or Hub Pages

- `docs/README.md` - docs hub and audience map
- `docs/user-manual.md` - short manual landing page that routes readers to guided workflows
- `docs/backends.md` - backend setup and selection reference
- `docs/cli.md` - CLI reference, flags, and non-walkthrough examples
- `docs/gui.md` - GUI surface reference and behavior map
- `docs/configuration.md` - config reference
- `docs/http-api.md` - route and payload reference
- `docs/local-http-quick-reference.md` - contributor seam map for the local API
- `docs/addons.md` - addon model overview and stable extension contract
- `docs/reports.md` - report/output reference
- `docs/troubleshooting.md` - troubleshooting index and recovery reference

### Add A New Guided Workflow Layer

Proposed tree:

```text
docs/
  guides/
    getting-started/
      windows-installer.md
      first-cli-review.md
      first-gui-session.md
    review-workflows/
      diff-review.md
      partial-project.md
      specification-review.md
      ai-fix.md
      restore-and-finalize.md
    benchmarks/
      run-benchmarks.md
      compare-benchmark-runs.md
      author-benchmark-fixture.md
    automation/
      tool-automation.md
      local-http-review-workflow.md
      local-http-events-and-artifacts.md
    addons/
      build-basic-addon.md
      review-generated-addon-preview.md
      ship-and-debug-addon.md
    recovery/
      common-recovery-paths.md
```

### Add Focused Reference Pages For The Two Expansion Areas

API reference split:

- `docs/http-api.md` - stable route inventory, payloads, response shapes, and boundary rules
- `docs/local-http-quick-reference.md` - contributor implementation seam map
- new `docs/http-api-recipes.md` - compact consumer cookbook for common integration patterns

Addon reference split:

- `docs/addons.md` - addon system overview, discovery rules, permissions, and supported extension points
- new `docs/addon-manifest-reference.md` - manifest schema, entry point fields, compatibility keys, and validation rules
- new `docs/addon-review-workflow.md` - generated-preview review and approval reference for CLI and GUI surfaces

## Role Of The New Manual Landing Page

`docs/user-manual.md` should stop trying to be the full walkthrough body.

Its job in the new structure is:

- explain how the docs are organized
- route users to the right guide quickly
- keep a short chooser for common goals
- link each workflow to its deeper reference pages when the reader needs full flags, config, or contracts

Target shape:

- opening summary
- choose-your-path table or bullet list
- grouped guide links by user goal
- short recovery section that links into the deeper recovery guide and troubleshooting reference

## How Images Should Work

Use images as supporting workflow anchors, not decoration.

Proposed conventions:

- keep screenshots in `docs/images/guides/`
- group by workflow slug, for example `docs/images/guides/first-gui-session/`
- prefer PNG for GUI captures and SVG only for diagrams that are authored, not screenshots
- add alt text that describes the user-visible state rather than the file name
- keep one screenshot per meaningful state change, not one screenshot per paragraph
- when a guide has more than one screenshot, align them to numbered steps so the image placement stays stable during edits

Recommended screenshot classes for the first pass:

- first GUI launch and backend setup state
- partial-project file selection state
- benchmark compare workflow
- generated addon review surface
- local HTTP settings/discovery surface in the GUI

The existing screenshot tooling should stay the preferred capture path for reproducible GUI images.

## Step-By-Step Guide Template

Each new guide should follow the same shape:

1. What this guide is for
2. Preconditions
3. Expected result
4. Step-by-step actions
5. What to check if something looks wrong
6. Related reference docs

This keeps the guides compact and makes images easier to place because each screenshot belongs to a concrete state in the step list.

## API Documentation Expansion Plan

The API material should separate three audiences that are currently mixed together:

- users who want to drive the tool from another local script
- contributors changing route behavior or event semantics
- maintainers validating local API boundary rules and GUI embedding

Recommended outcome:

- keep `docs/http-api.md` as the authoritative reference page
- keep `docs/local-http-quick-reference.md` as the contributor seam map
- add `docs/http-api-recipes.md` for concrete tasks such as:
  - start the server and submit a dry run
  - submit a real review and poll job state
  - stream events over SSE and fetch the final report
  - fetch artifacts safely and understand output-path restrictions

This gives the API a clearer progression:

- task guide first
- contract reference second
- code seam map when implementation changes are needed

## Addon Documentation Expansion Plan

The addon material should separate four concerns that are currently bundled together:

- what addons can do
- how addon manifests are shaped
- how to build a simple addon from scratch
- how to review and approve a generated addon preview

Recommended outcome:

- keep `docs/addons.md` as the stable addon-system overview
- add `docs/addon-manifest-reference.md` for exact manifest and entry-point details
- add `docs/addon-review-workflow.md` for the preview, diff, approve, and reject flow
- add guided walkthroughs under `docs/guides/addons/` for:
  - first addon creation
  - generated preview review in GUI and CLI
  - packaging/debugging an addon during development

This gives addon docs a cleaner split between platform contract and author tutorial.

## Migration Order

Phase 1: manual and workflow extraction

- trim `docs/user-manual.md` into a landing page
- create the highest-value workflow guides under `docs/guides/`
- move existing long-form workflow sections into those guide pages with minimal wording churn first

Phase 2: API split

- keep `docs/http-api.md` authoritative
- add `docs/http-api-recipes.md`
- move tutorial-style request sequences out of the main reference page when duplicated

Phase 3: addon split

- keep `docs/addons.md` authoritative for system behavior
- add manifest and review-workflow references
- add step-by-step addon authoring guides

Phase 4: image pass

- capture reproducible screenshots for the extracted guides
- add diagrams only where screenshots are insufficient, such as API/job/event flow or addon preview approval flow

## First Concrete File Moves

The lowest-risk first extraction set is:

- `docs/user-manual.md` -> keep only chooser and high-level routing
- new `docs/guides/getting-started/first-cli-review.md`
- new `docs/guides/getting-started/first-gui-session.md`
- new `docs/guides/review-workflows/diff-review.md`
- new `docs/guides/addons/build-basic-addon.md`
- new `docs/http-api-recipes.md`
- new `docs/addon-manifest-reference.md`

That first set is enough to prove the structure before migrating every workflow section.

## Acceptance Criteria For This Phase

- the user manual becomes a routing page instead of a monolith
- at least one getting-started guide, one review workflow guide, one API recipe page, and one addon authoring guide exist in the new structure
- image placement conventions are documented before a larger screenshot pass begins
- API usage docs clearly separate task walkthroughs from route reference
- addon docs clearly separate authoring tutorials from manifest/reference material
- the docs hub still points readers to the right place without requiring them to understand the whole tree first

## Recommended Next Execution Slice

1. Extract `CLI First Review` and `GUI First Session` from `docs/user-manual.md` into new guide pages.
2. Add `docs/http-api-recipes.md` with two concrete flows: submit/poll and submit/stream/fetch.
3. Add `docs/addon-manifest-reference.md` and move manifest-shape detail out of `docs/addons.md` only after the new reference exists.
4. Update `docs/README.md` and `docs/user-manual.md` links after those first pages land.