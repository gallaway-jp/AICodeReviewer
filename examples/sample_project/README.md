# Sample Project with Intentional Code Issues

This is a deliberately flawed project used to demonstrate AICodeReviewer safely and predictably.

## Project Structure

```
sample_project/
├── user_auth.py        # Security vulnerabilities
├── data_processor.py   # Performance issues
├── calculator.py       # Best practices violations
├── api_handler.py      # Error handling problems
└── utils.py           # Maintainability concerns
```

## Intentional Issues by Category

### Security Issues (user_auth.py)
- SQL injection vulnerability (unsanitized inputs)
- Weak MD5 password hashing
- Unsafe pickle deserialization
- Hardcoded credentials
- Predictable session tokens

### Performance Issues (data_processor.py)
- String concatenation in loops
- O(n²) nested loop complexity
- Repeated file I/O operations
- Inefficient list operations
- Multiple passes over data
- Blocking sleep instead of async

### Best Practices Violations (calculator.py)
- Magic numbers without constants
- Poor variable/function naming
- Class naming conventions ignored
- Methods doing too many things
- Duplicate code
- Global mutable state
- Functions with too many parameters
- Missing error handling

### Error Handling Issues (api_handler.py)
- No exception handling on network calls
- Assuming data structure without validation
- File operations without try-catch
- Bare except clauses
- No input validation

### Maintainability Issues (utils.py)
- Deep nested conditionals
- Very long functions
- Single letter variable names
- Complex logic without comments

## Running Reviews

Use this project to validate one review type at a time:

```bash
# Security review
aicodereviewer examples/sample_project --type security --programmers "Demo User" --reviewers "AI Reviewer"

# Performance review
aicodereviewer examples/sample_project --type performance --programmers "Demo User" --reviewers "AI Reviewer"

# Best practices review
aicodereviewer examples/sample_project --type best_practices --programmers "Demo User" --reviewers "AI Reviewer"

# Error handling review
aicodereviewer examples/sample_project --type error_handling --programmers "Demo User" --reviewers "AI Reviewer"

# Maintainability review
aicodereviewer examples/sample_project --type maintainability --programmers "Demo User" --reviewers "AI Reviewer"

# Dry run
aicodereviewer examples/sample_project --type security --dry-run
```

## Expected Findings

The AI reviewer should identify and provide specific recommendations for all intentional issues listed above, demonstrating its ability to:
- Detect security vulnerabilities with severity ratings
- Identify performance bottlenecks and suggest optimizations
- Recognize code style and best practice violations
- Find error handling gaps
- Suggest maintainability improvements

## Related Docs

- [examples/README.md](../README.md)
- [DEMO_WALKTHROUGH.md](../DEMO_WALKTHROUGH.md)
- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md)
