# Review Types Reference

AICodeReviewer exposes 22 selectable review types.

## Quality

| Key | Label | Focus |
|---|---|---|
| `security` | Security Audit | Vulnerabilities, unsafe patterns, OWASP and CWE-style risks |
| `performance` | Performance | Inefficient algorithms, redundant work, blocking behavior |
| `best_practices` | Best Practices | Style, structure, SOLID, DRY, maintainable code shape |
| `maintainability` | Maintainability | Readability, responsibility boundaries, long-term code health |
| `dead_code` | Dead Code | Unused, unreachable, or obsolete code paths with concrete evidence |
| `documentation` | Documentation | Missing docs, poor comments, weak developer guidance |
| `testing` | Testing | Coverage gaps, brittle tests, untested critical paths |
| `error_handling` | Error Handling | Missing guards, exception misuse, resilience gaps |
| `complexity` | Complexity Analysis | Cyclomatic and cognitive complexity, deep nesting |
| `concurrency` | Concurrency Safety | Race conditions, shared-state hazards, synchronization gaps |
| `data_validation` | Data Validation | Input validation, sanitization, contract enforcement |
| `regression` | Regression Analysis | Risk of breaking existing behavior or contracts |
| `ui_ux` | UI/UX Review | Usability, interaction flow, hierarchy, and interface clarity |

## Architecture

| Key | Label | Focus |
|---|---|---|
| `scalability` | Scalability | Throughput and growth bottlenecks |
| `compatibility` | Compatibility | Platform, runtime, and environment compatibility risks |
| `architecture` | Architecture | Layering, abstractions, dependency boundaries |
| `dependency` | Dependency Analysis | Dependency health, outdated or risky packages |
| `api_design` | API Design | Public interface design, consistency, usability |

## Compliance

| Key | Label | Focus |
|---|---|---|
| `accessibility` | Accessibility | WCAG-oriented UI and interaction concerns |
| `license` | License Compliance | Dependency and usage licensing compatibility |
| `localization` | Localization / i18n | Hard-coded strings and translation readiness |
| `specification` | Specification Match | Code behavior compared to an external requirements file |

`ui_ux` and `accessibility` overlap, but they are not the same review. Use `ui_ux` for task flow, hierarchy, affordances, empty/error/loading states, and general usability. Use `accessibility` for WCAG-oriented issues like keyboard flow, semantics, contrast, and assistive technology support.

`dead_code` and `maintainability` overlap, but they are not the same review. Use `dead_code` when you want evidence-backed findings about unreachable branches, unused helpers, stale flags, dormant handlers, or obsolete compatibility paths. Use `maintainability` for broader readability, coupling, complexity, and refactor pressure.

## Notes

- `--type all` selects all 22 user-selectable review types.
- Internal processing prompts such as interaction analysis and architectural review are not directly selectable via `--type`.
- `specification` requires `--spec-file` in the CLI or a spec file in the GUI.

## Choosing Review Types

Prefer targeted bundles over very wide sessions. The current prompt-interference analysis shows that prompt size grows from roughly `7.8k` characters for a single-type session to about `25k` at eight selected types and about `68k` at a 22-type "all" session, and the existing empirical sample showed that wide sessions mixed real target-retention drift with command-level failures. In practice:

- treat `3` to `6` related review types as the normal operating range for one session
- treat `7` or `8` review types as an upper bound for exploratory runs, not a default workflow
- avoid using `--type all` as the primary quality signal for release checks; use narrower passes instead
- keep `specification` focused because it introduces an external requirements document and materially increases prompt pressure
- keep `license` focused because its guidance block is large and tends to overlap with `dependency` classification language

Recommended starting sets:

- Security-sensitive services: `security,error_handling,data_validation,dependency`
- Large codebases: `maintainability,dead_code,complexity,architecture`
- API-heavy systems: `api_design,compatibility,testing,regression`
- Product release check: `best_practices,testing,regression,documentation`
- Cleanup and refactor passes: `dead_code,maintainability,testing,regression`
- Frontend and desktop apps: `ui_ux,accessibility,localization,regression`

Recommended stable bundles:

- Runtime safety: `security,error_handling,data_validation,dependency`
- Code health: `best_practices,maintainability,dead_code,complexity,regression`
- Interface and platform: `api_design,compatibility,architecture,scalability`
- Product surface: `ui_ux,accessibility,localization,documentation`
- Release safety: `testing,regression,error_handling,compatibility`

Recommended narrow or isolated passes:

- `specification` by itself, or at most with `api_design`, `data_validation`, or `regression` when you are validating an external contract
- `license` by itself, or with `dependency` only when you are auditing packaging and notice obligations together
- `architecture` should usually stay with `api_design`, `compatibility`, or `scalability`, not with broad quality bundles that already include heavy classification guidance

High-pressure review types:

- `license`
- `compatibility`
- `error_handling`
- `architecture`
- `maintainability`
- `specification`
- `dependency`
- `scalability`

When one of these is selected, prefer smaller sessions and avoid stacking several of them into the same review unless you have a specific reason to compare their interaction.

For frontend and desktop apps, the holistic benchmark suite now includes UI/UX fixtures for missing feedback states, form-recovery friction, desktop busy-state feedback gaps, destructive confirmation-flow failures, desktop settings discoverability issues, wizard-orientation gaps, and cross-tab preference dependency failures, so prompt or parser changes can be checked against concrete usability scenarios instead of only generic wording.

## Related Guides

- [CLI Guide](cli.md)
- [Configuration Reference](configuration.md)
- [Examples](../examples/README.md)