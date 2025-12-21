# AICodeReviewer Demo - What to Expect

This guide shows you what to expect when running the AICodeReviewer on the sample project.

## Project Overview

The sample project consists of 5 Python files with **40+ intentional code issues** across multiple categories.

## Running Your First Review

Let's walk through a **Security Review** example:

### Step 1: Start the Review

```bash
python -m aicodereviewer examples/sample_project \
  --type security \
  --programmers "Demo User" \
  --reviewers "AI Reviewer"
```

### Step 2: Initial Scan Output

```
Scanning examples/sample_project - Scope: entire project (Output Language: en)...
Found 5 files to review (estimated time: 0m 40s)
Collecting review issues from 5 files...
```

### Step 3: AI Analysis Per File

```
Analyzing examples/sample_project/user_auth.py...
Analyzing examples/sample_project/data_processor.py...
Analyzing examples/sample_project/calculator.py...
Analyzing examples/sample_project/api_handler.py...
Analyzing examples/sample_project/utils.py...
```

### Step 4: Interactive Issue Review

For each issue found, you'll see:

```
================================================================================
ISSUE 1/8
================================================================================
File: examples/sample_project/user_auth.py
Type: security
Severity: critical
Code snippet:
def login(self, username, password):
    """Authenticate user - SECURITY ISSUE: SQL injection vulnerability"""
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    self.cursor.execute(query)
...

AI Feedback:
CRITICAL SECURITY VULNERABILITY: SQL Injection

The login method is vulnerable to SQL injection attacks. An attacker could bypass 
authentication or extract sensitive data by providing malicious input.

Example attack:
  username: admin' OR '1'='1
  password: anything

RECOMMENDATION:
1. Use parameterized queries with placeholders
2. Never concatenate user input into SQL strings
3. Use an ORM like SQLAlchemy for safer database operations

Fixed code example:
  query = "SELECT * FROM users WHERE username=? AND password=?"
  self.cursor.execute(query, (username, password))

SEVERITY: Critical - This vulnerability allows complete authentication bypass
IMPACT: Data breach, unauthorized access, potential database compromise

Status: pending

Actions:
  1. RESOLVED - Mark as resolved (program will verify)
  2. IGNORE - Ignore this issue (requires reason)
  3. AI FIX - Let AI fix the code
  4. VIEW CODE - Show full file content

Choose action (1-4):
```

### Step 5: Your Choices

#### Option 1: Mark as Resolved
If you fix the issue manually, choose `1`:
```
Choose action (1-4): 1
✅ Issue marked as resolved!
```
The AI will re-analyze to verify the fix.

#### Option 2: Ignore with Reason
If you want to skip this issue, choose `2`:
```
Choose action (1-4): 2
Enter reason for ignoring this issue: This is a demo file, not production code
✅ Issue ignored with reason provided.
```

#### Option 3: Let AI Fix It
Choose `3` to see and apply an AI-generated fix:
```
Choose action (1-4): 3

🤖 AI suggests the following fix:
================================================================================
--- a/user_auth.py
+++ b/user_auth.py
@@ -15,8 +15,8 @@ class UserAuth:
     
     def login(self, username, password):
-        """Authenticate user - SECURITY ISSUE: SQL injection vulnerability"""
-        query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
-        self.cursor.execute(query)
+        """Authenticate user with parameterized query"""
+        query = "SELECT * FROM users WHERE username=? AND password=?"
+        self.cursor.execute(query, (username, password))
         result = self.cursor.fetchone()
         return result is not None
================================================================================
Apply this AI fix? (y/n): y
📁 Backup created: user_auth.py.backup
✅ AI fix applied successfully!
```

#### Option 4: View Full Code
Choose `4` to see the complete file:
```
Choose action (1-4): 4

Full file content (examples/sample_project/user_auth.py):
--------------------------------------------------
"""
User authentication module with intentional security vulnerabilities.
"""
import pickle
import hashlib
import sqlite3

[... full file content ...]
--------------------------------------------------
```

### Step 6: Continue Through All Issues

The process repeats for each issue. You'll see issues for:
- SQL injection (critical)
- Weak MD5 hashing (high)
- Unsafe pickle (high)
- Hardcoded credentials (medium)
- Predictable tokens (medium)

### Step 7: Final Report

After handling all issues:

```
Generating review report...
Saved JSON review report to review_report_20251221_160530.json
Saved human-readable summary to review_report_20251221_160530_summary.txt
```

## Expected Results by Review Type

### Security Review (~5-8 issues)

**Critical Issues:**
- SQL injection in `user_auth.py`
- Unsafe pickle deserialization

**High Issues:**
- Weak MD5 password hashing
- Bare exception handling

**Medium Issues:**
- Hardcoded credentials
- Predictable session tokens

**Quality Score:** ~40/100 (Poor - Critical vulnerabilities present)

---

### Performance Review (~6-8 issues)

**High Issues:**
- O(n²) duplicate finding algorithm
- String concatenation in loops

**Medium Issues:**
- Repeated file I/O operations
- Multiple data passes instead of single comprehension
- Inefficient list operations

**Low Issues:**
- Blocking sleep calls

**Quality Score:** ~55/100 (Fair - Multiple performance bottlenecks)

---

### Best Practices Review (~8-10 issues)

**Medium Issues:**
- Magic numbers (0.175 tax rate)
- Poor naming (f, calc, doEverything)
- Global mutable state
- Code duplication

**Low Issues:**
- Too many function parameters
- Methods doing multiple things
- Non-standard naming conventions

**Quality Score:** ~60/100 (Fair - Multiple style violations)

---

### Error Handling Review (~6-7 issues)

**High Issues:**
- No exception handling on network calls
- Bare except clauses catching all exceptions

**Medium Issues:**
- File operations without try-catch
- No input validation
- Assuming data structure without checks

**Quality Score:** ~50/100 (Fair - Missing critical error handling)

---

### Maintainability Review (~3-5 issues)

**High Issues:**
- Deep nested conditionals (5+ levels)
- Very long functions (50+ lines, multiple responsibilities)

**Medium Issues:**
- Cryptic variable names (a, b, c, x, y, z)
- Complex logic without documentation

**Quality Score:** ~65/100 (Fair - Some maintainability concerns)

---

## Summary Report Example

After completing a review, the summary file will look like:

```
AI Code Review Report
==================================================

Project: examples/sample_project
Review Type: security
Scope: project
Files Scanned: 5
Quality Score: 42/100
Programmers: Demo User
Reviewers: AI Reviewer
Generated: 2025-12-21 16:05:30
Language: en

Issues Summary:
------------------------------
Resolved: 2
Ignored: 1
Pending: 5

Detailed Issues:
==================================================

Issue 1:
  File: examples/sample_project/user_auth.py
  Type: security
  Severity: critical
  Status: resolved
  Description: Review feedback for user_auth.py
  Code: def login(self, username, password):
    """Authenticate user - SECURITY ISSUE: SQL injection vulnerability"""
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"...
  AI Feedback: CRITICAL SECURITY VULNERABILITY: SQL Injection

The login method is vulnerable to SQL injection attacks...

[... continues for all issues ...]
```

## Tips for Demo

1. **Start with Security** - Shows the most dramatic findings (critical vulnerabilities)
2. **Try AI Fix** - Demonstrates the automated fix generation
3. **Compare Review Types** - Run multiple types to see different perspectives
4. **Check Quality Scores** - Watch how they improve as you fix issues
5. **Review Generated Reports** - See both JSON (for tools) and summary (for humans)

## Next Steps

After exploring the demo:

1. **Run on real code** - Try your own projects
2. **Customize config** - Enable parallel processing for speed
3. **Integrate with CI/CD** - Add to your pipeline
4. **Use diff scope** - Review pull requests: `--scope diff --commits HEAD~1..HEAD`
5. **Try different languages** - Add `--lang ja` for Japanese output

## Questions?

See the main [README.md](../README.md) for:
- Installation instructions
- AWS Bedrock setup
- Configuration options
- Complete feature documentation
