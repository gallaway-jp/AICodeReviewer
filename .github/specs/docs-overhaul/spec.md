# Documentation Overhaul Spec

## Purpose

Replace the existing mixed documentation set with a curated, maintainable documentation system for both end users and contributors.

## Goals

- replace generated HTML docs as the primary documentation surface
- make the root README concise and task-oriented
- provide complete user guides for setup, backends, CLI, GUI, configuration, reports, and troubleshooting
- provide contributor guides for architecture and development workflow
- keep examples focused on demo usage instead of full product reference

## Non-Goals

- changing runtime behavior unless a documentation bug reveals a critical product bug
- introducing a static-site generator in the first phase
- documenting every internal helper as public API surface

## Acceptance Criteria

1. The root README links to curated docs instead of serving as the only reference.
2. `docs/README.md` becomes the maintained docs hub.
3. Generated HTML docs are removed from the primary documentation set.
4. User-facing docs exist for backend setup, CLI, GUI, configuration, reports, review types, and troubleshooting.
5. Contributor-facing docs exist for architecture and contribution workflow.
6. Examples remain available but are clearly positioned as walkthrough material.
7. Documentation statements are validated against code and tests.

## Information Architecture

- `README.md` -> front door
- `docs/README.md` -> curated docs hub
- `docs/getting-started.md` -> first-run guide
- `docs/backends.md` -> backend setup and selection
- `docs/cli.md` -> CLI reference and workflows
- `docs/gui.md` -> GUI workflows
- `docs/configuration.md` -> config reference
- `docs/review-types.md` -> review type catalog
- `docs/reports.md` -> outputs and report behavior
- `docs/troubleshooting.md` -> common failure modes and fixes
- `docs/architecture.md` -> contributor architecture overview
- `docs/contributing.md` -> contribution workflow
- `examples/` -> walkthroughs and sample project usage only

## Validation Checklist

- confirm backend names and setup steps match code
- confirm review type list matches `REVIEW_TYPE_KEYS`
- confirm config sections and defaults match `config.py`
- confirm GUI tabs and workflows match current implementation
- confirm report outputs match reporter behavior

## Phase 1 Deliverables

- repo-local spec file
- rewritten root README
- new docs hub and first curated docs pages
- examples landing page aligned to new docs structure

## Follow-Up Work

- refresh example walkthroughs to match the new docs tone and structure
- add screenshots or diagrams where useful
- decide whether a generated API reference should return in a later phase