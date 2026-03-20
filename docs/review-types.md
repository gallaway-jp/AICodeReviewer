# Review Types Reference

AICodeReviewer exposes 20 selectable review types.

## Quality

| Key | Label | Focus |
|---|---|---|
| `security` | Security Audit | Vulnerabilities, unsafe patterns, OWASP and CWE-style risks |
| `performance` | Performance | Inefficient algorithms, redundant work, blocking behavior |
| `best_practices` | Best Practices | Style, structure, SOLID, DRY, maintainable code shape |
| `maintainability` | Maintainability | Readability, responsibility boundaries, long-term code health |
| `documentation` | Documentation | Missing docs, poor comments, weak developer guidance |
| `testing` | Testing | Coverage gaps, brittle tests, untested critical paths |
| `error_handling` | Error Handling | Missing guards, exception misuse, resilience gaps |
| `complexity` | Complexity Analysis | Cyclomatic and cognitive complexity, deep nesting |
| `concurrency` | Concurrency Safety | Race conditions, shared-state hazards, synchronization gaps |
| `data_validation` | Data Validation | Input validation, sanitization, contract enforcement |
| `regression` | Regression Analysis | Risk of breaking existing behavior or contracts |

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

## Notes

- `--type all` selects all 20 user-selectable review types.
- Internal processing prompts such as interaction analysis and architectural review are not directly selectable via `--type`.
- `specification` requires `--spec-file` in the CLI or a spec file in the GUI.

## Choosing Review Types

Recommended starting sets:

- Security-sensitive services: `security,error_handling,data_validation,dependency`
- Large codebases: `maintainability,complexity,architecture,scalability`
- API-heavy systems: `api_design,compatibility,testing,regression`
- Product release check: `best_practices,testing,regression,documentation`

## Related Guides

- [CLI Guide](cli.md)
- [Configuration Reference](configuration.md)
- [Examples](../examples/README.md)