# AICodeReviewer Demo Examples

This directory contains demonstration materials for the AICodeReviewer tool, including a sample project with intentional code issues and scripts to run various review types.

## Contents

- **sample_project/** - A Python project with intentional security, performance, and quality issues
- **run_demo.py** - Script to run different review types on the sample project
- **demo_outputs/** - Generated review reports (created when you run reviews)

## Quick Start

### 1. Review the Sample Project

The sample project contains 5 Python files with different types of intentional issues:

```bash
cd examples/sample_project
cat README.md  # See detailed list of intentional issues
```

### 2. Run Individual Reviews

#### Security Review
Identifies SQL injection, weak hashing, hardcoded credentials, etc.

```bash
python -m aicodereviewer examples/sample_project \
  --type security \
  --programmers "Demo User" \
  --reviewers "AI Reviewer" \
  --lang en
```

#### Performance Review
Finds inefficient algorithms, repeated operations, blocking calls, etc.

```bash
python -m aicodereviewer examples/sample_project \
  --type performance \
  --programmers "Demo User" \
  --reviewers "AI Reviewer" \
  --lang en
```

#### Best Practices Review
Catches naming violations, magic numbers, code duplication, etc.

```bash
python -m aicodereviewer examples/sample_project \
  --type best_practices \
  --programmers "Demo User" \
  --reviewers "AI Reviewer" \
  --lang en
```

#### Error Handling Review
Detects missing exception handling, bare except clauses, validation gaps, etc.

```bash
python -m aicodereviewer examples/sample_project \
  --type error_handling \
  --programmers "Demo User" \
  --reviewers "AI Reviewer" \
  --lang en
```

#### Maintainability Review
Identifies complex functions, deep nesting, poor variable names, etc.

```bash
python -m aicodereviewer examples/sample_project \
  --type maintainability \
  --programmers "Demo User" \
  --reviewers "AI Reviewer" \
  --lang en
```

### 3. Interactive Review Workflow

When you run a review, AICodeReviewer will:

1. **Scan** the project and identify files to review
2. **Analyze** each file using AWS Bedrock AI
3. **Present** each issue with details and code snippets
4. **Prompt** you to choose an action for each issue:
   - **RESOLVED** - Mark as fixed (AI will verify)
   - **IGNORE** - Skip with a reason
   - **AI FIX** - Let AI generate a fix (shows diff first)
   - **VIEW CODE** - See full file context

5. **Generate** JSON and summary reports when complete

### 4. Review the Results

After completing a review, you'll get two files:

- `review_report_YYYYMMDD_HHMMSS.json` - Complete structured data
- `review_report_YYYYMMDD_HHMMSS_summary.txt` - Human-readable summary

Example summary output:

```
AI Code Review Report
==================================================

Project: examples/sample_project
Review Type: security
Scope: project
Files Scanned: 5
Quality Score: 45/100
Programmers: Demo User
Reviewers: AI Reviewer
Generated: 2025-12-21 16:00:00
Language: en

Issues Summary:
------------------------------
Pending: 8
Resolved: 2
Ignored: 1

Detailed Issues:
==================================================

Issue 1:
  File: examples/sample_project/user_auth.py
  Type: security
  Severity: critical
  Status: pending
  Description: Review feedback for user_auth.py
  AI Feedback: Critical SQL injection vulnerability detected in login method...
```

## Expected Findings by Review Type

### Security Review (user_auth.py)
- **Critical**: SQL injection in login function
- **High**: Weak MD5 password hashing (use bcrypt/argon2)
- **High**: Unsafe pickle deserialization (code execution risk)
- **Medium**: Hardcoded admin credentials
- **Medium**: Predictable session tokens (use secrets module)

### Performance Review (data_processor.py)
- **High**: O(n²) duplicate finding algorithm (use set)
- **High**: String concatenation in loop (use join)
- **Medium**: Repeated file I/O (read once, cache)
- **Medium**: Multiple passes over data (use generator/comprehension)
- **Low**: Blocking sleep (consider async/await)

### Best Practices Review (calculator.py)
- **Medium**: Magic number 0.175 (define TAX_RATE constant)
- **Medium**: Poor function names (f, doEverything, p)
- **Medium**: Non-PascalCase class name (calc)
- **Low**: Too many function parameters (use config object)
- **Low**: Global mutable state (encapsulate in class)

### Error Handling Review (api_handler.py)
- **High**: No exception handling on network requests
- **High**: Bare except clause (catches all exceptions)
- **Medium**: Assuming data structure without validation
- **Medium**: File operations without error handling
- **Low**: No input validation on JSON parsing

### Maintainability Review (utils.py)
- **High**: Deep nested conditionals (5+ levels)
- **High**: Very long function (50+ lines, multiple responsibilities)
- **Medium**: Single letter variable names (a, b, c, x, y, z)
- **Low**: Complex logic without documentation

## Configuration

You can adjust how the tool processes these files by editing `config.ini`:

```ini
[processing]
batch_size = 5                          # Files per batch
enable_parallel_processing = false      # Enable for faster reviews

[performance]
max_file_size_mb = 10                   # Skip files larger than this
```

## Tips

1. **Start with security** - Critical vulnerabilities should be addressed first
2. **Enable parallel processing** - For larger projects, set `enable_parallel_processing = true`
3. **Save specific reports** - Use `--output` to name your reports meaningfully
4. **Try different languages** - Add `--lang ja` for Japanese feedback
5. **Review diffs only** - Use `--scope diff --commits HEAD~1..HEAD` for PR reviews

## Next Steps

After exploring these examples:

1. Run AICodeReviewer on your own projects
2. Integrate into your CI/CD pipeline
3. Use `--scope diff` for pull request reviews
4. Customize review types based on your needs
5. Set up AWS Bedrock authentication (see main README.md)

## Troubleshooting

If you encounter issues:

```bash
# Check your AWS profile is set
python -m aicodereviewer --set-profile your-profile-name

# Enable debug logging
# Edit config.ini: log_level = DEBUG

# Verify Python environment
python --version  # Should be 3.9+
```

For more information, see the main project [README.md](../README.md).
