# AICodeReviewer Demo Quick Reference

## Sample Project Files

| File | Issues | Review Type |
|------|--------|-------------|
| `user_auth.py` | SQL injection, weak hashing, unsafe deserialization | Security |
| `data_processor.py` | O(n²) complexity, string concat, file I/O in loops | Performance |
| `calculator.py` | Magic numbers, poor naming, global state | Best Practices |
| `api_handler.py` | No exception handling, bare except, no validation | Error Handling |
| `utils.py` | Deep nesting, long functions, cryptic names | Maintainability |

## One-Line Review Commands

```bash
# Security
python -m aicodereviewer examples/sample_project --type security --programmers "Demo" --reviewers "AI"

# Performance  
python -m aicodereviewer examples/sample_project --type performance --programmers "Demo" --reviewers "AI"

# Best Practices
python -m aicodereviewer examples/sample_project --type best_practices --programmers "Demo" --reviewers "AI"

# Error Handling
python -m aicodereviewer examples/sample_project --type error_handling --programmers "Demo" --reviewers "AI"

# Maintainability
python -m aicodereviewer examples/sample_project --type maintainability --programmers "Demo" --reviewers "AI"
```

## Interactive Actions

When presented with an issue:

- **1 (RESOLVED)** - Mark as fixed; AI verifies the resolution
- **2 (IGNORE)** - Skip issue; must provide reason
- **3 (AI FIX)** - Generate automatic fix; shows diff first
- **4 (VIEW CODE)** - Display full file content for context

## Key Intentional Issues

### Critical Security (user_auth.py)
```python
# SQL Injection - Line 17
query = f"SELECT * FROM users WHERE username='{username}'"
# FIX: Use parameterized queries
query = "SELECT * FROM users WHERE username=? AND password=?"
```

### Performance O(n²) (data_processor.py)
```python
# Nested loops - Line 19
for i in range(len(numbers)):
    for j in range(len(numbers)):
        if i != j and numbers[i] == numbers[j]:
# FIX: Use set for O(n) complexity
duplicates = [x for x in set(numbers) if numbers.count(x) > 1]
```

### Best Practices (calculator.py)
```python
# Magic number - Line 8
return amount * 0.175
# FIX: Use named constant
TAX_RATE = 0.175
return amount * TAX_RATE
```

### Error Handling (api_handler.py)
```python
# No exception handling - Line 13
response = requests.get(f"{self.base_url}/{endpoint}")
return response.json()
# FIX: Add try-except
try:
    response = requests.get(f"{self.base_url}/{endpoint}", timeout=10)
    response.raise_for_status()
    return response.json()
except requests.RequestException as e:
    logger.error(f"API request failed: {e}")
    return None
```

### Maintainability (utils.py)
```python
# Deep nesting - Line 8
if age >= 18:
    if income > 30000:
        if credit_score > 600:
            if employment_status == "employed":
                if has_collateral:
# FIX: Early returns
if age < 18:
    return "rejected"
if income <= 30000:
    return "rejected"
# ... etc
```

## Expected Issue Counts

| Review Type | Expected Issues | Severity Distribution |
|-------------|-----------------|----------------------|
| Security | 5-8 | 2-3 Critical, 2-3 High, 1-2 Medium |
| Performance | 6-8 | 2-3 High, 3-4 Medium, 1-2 Low |
| Best Practices | 8-10 | 3-4 Medium, 4-6 Low |
| Error Handling | 6-7 | 2-3 High, 2-3 Medium, 1-2 Low |
| Maintainability | 3-5 | 2-3 High, 1-2 Medium |

## Output Files

After review completion:

- `review_report_YYYYMMDD_HHMMSS.json` - Full structured data
- `review_report_YYYYMMDD_HHMMSS_summary.txt` - Human-readable summary

## Quality Score Interpretation

- **90-100**: Excellent - Minor or no issues
- **70-89**: Good - Some issues, mostly low severity
- **50-69**: Fair - Multiple medium issues
- **30-49**: Poor - Several high severity issues
- **0-29**: Critical - Multiple critical issues

The sample project should score around **40-50** before fixes due to intentional critical security issues.
