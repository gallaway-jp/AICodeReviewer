# Milestone 12 User Manual Foundation

## What changed

- Added `docs/user-manual.md` as the initial task-oriented manual entry point for end users.
- Routed the new manual through the docs hub, getting-started guide, and root README so users can find it before the deeper reference pages.
- Updated the platform-extensibility spec to mark Milestone 12 as in progress with the manual foundation now in place.

## What the manual covers now

- first CLI review workflow
- first GUI session workflow
- tool-mode automation sequence
- basic addon loading path using checked-in examples
- local HTTP user workflow
- common recovery paths and where to read deeper troubleshooting material

## Notes

- This slice is a manual foundation, not Milestone 12 completion.
- The current page intentionally links out to the maintained reference guides instead of duplicating every flag, route, and setting.
- Existing durable GUI screenshots were reused where they improved comprehension for the initial manual.

## Files updated

- `docs/user-manual.md`
- `docs/README.md`
- `docs/getting-started.md`
- `README.md`
- `.github/specs/platform-extensibility/spec.md`

## Next logical slices

- expand the manual with more detailed task walkthroughs for diff reviews, AI Fix workflows, session restore/finalize, and benchmark usage
- add user-level HTTP workflow examples that are more task-oriented than the route reference
- add targeted annotated captures only where they materially improve the manual instead of mirroring every existing screenshot