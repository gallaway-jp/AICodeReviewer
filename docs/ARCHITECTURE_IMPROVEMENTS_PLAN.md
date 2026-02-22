# Implementation Plan: Fixing Review System Weaknesses

## Overview

This document outlines a detailed 10-part plan to address architectural weaknesses in the AICodeReviewer review system. The plan fixes issues with:

1. **No broader codebase context** — files reviewed in isolation
2. **Brittle delimiter-dependent parsing** — failures if model deviates from format
3. **Static batch sizing** — inefficient API usage and expensive recovery
4. **Limited cross-issue understanding** — no coordination between concerns
5. **No historical/behavioral context** — missing commit history and diffs
6. **Brittle severity extraction** — fragile keyword matching
7. **No project type awareness** — generic reviews regardless of tech stack
8. **Expensive failure recovery** — 2–3x API calls on batch failures
9. **Cache invalidation issues** — stale file content across reviews
10. **Cannot detect architectural smells** — no cross-file analysis

---

## Part 1 — Project Context Collector (`context_collector.py`)

**Addresses:** #1 (No Broader Codebase Context), #7 (No Project Type Awareness)

**Purpose:** Build a lightweight "project summary" injected into every review prompt to provide architectural context and framework-specific guidance.

### Implementation Steps

1. **Create new file** `src/aicodereviewer/context_collector.py`

2. **Detect project type** — scan for framework markers:
   - `package.json`, `package-lock.json` → Node.js/JavaScript
   - `pyproject.toml`, `setup.py`, `requirements.txt` → Python
   - `Cargo.toml` → Rust
   - `pom.xml` → Java/Maven
   - `go.mod` → Go
   - `Gemfile` → Ruby
   - Other markers for C#, PHP, etc.
   - Framework detection: Django, Flask, FastAPI, Express, Next.js, Spring Boot, Rails, etc.

3. **Build a dependency graph** — parse imports across all scanned files:
   - For Python: parse `import`/`from` statements via regex or AST
   - For JavaScript: parse `import`/`require` statements
   - For Java: parse `import` statements
   - Produce a flat list of internal module relationships
   - Example: `scanner.py → config.py, models.py`

4. **Produce a project summary string** — compact block (~500 tokens) containing:
   - Detected language/framework/tools
   - Directory structure (top 2 levels only)
   - Module dependency edges (which files import which, top 20 edges)
   - Naming conventions detected (camelCase, snake_case, kebab-case)
   - Optional: count of files per type, approximate LOC

5. **Inject into system prompt** — modify `AIBackend._build_system_prompt()`:
   - Add optional parameter `project_context: Optional[str] = None`
   - Prepend as: `PROJECT CONTEXT:\n{project_context}\n\n` before the persona prompt

6. **Thread the context through the call chain**:
   - `collect_review_issues()` → builds context, passes to `_process_file_batch()`
   - `_process_file_batch()` → passes to `client.get_review()`
   - `client.get_review()` → passes to `_build_system_prompt()`

7. **Add config options** to `src/aicodereviewer/config.py`:
   ```ini
   [processing]
   enable_project_context = true
   context_max_tokens = 500
   ```

8. **Cache the context** — compute once per review session and reuse across all batches

### Expected Output Example

```
PROJECT CONTEXT:

Language: Python 3.11
Framework: CLI Application (Click/Typer pattern)
Tools: pytest, mypy, ruff, black

Key Files:
- reviewer.py — main review orchestration
- scanner.py — file discovery and diff parsing
- models.py — data structures
- backends/base.py — AI backend abstraction

Dependencies (top edges):
- reviewer.py → scanner.py, models.py, backends/base.py
- scanner.py → config.py
- backends/ → backends/base.py
- backends/bedrock.py → config.py, models.py

Naming: snake_case for functions/variables, PascalCase for classes
```

---

## Part 2 — Structured JSON Output Format

**Addresses:** #2 (Delimiter-Dependent Parsing), #6 (Brittle Severity Extraction)

**Purpose:** Replace free-text delimiters with a structured JSON contract for reliable parsing.

### Implementation Steps

1. **Define a JSON schema** for expected model output:

   ```json
   {
     "review_type": "security",
     "language": "en",
     "files": [
       {
         "filename": "src/app.py",
         "findings": [
           {
             "severity": "critical",
             "line": 42,
             "column": 10,
             "category": "security",
             "title": "SQL Injection Vulnerability",
             "description": "User input directly concatenated into SQL query without parameterization.",
             "code_context": "query = f\"SELECT * FROM users WHERE id = {user_id}\"",
             "suggestion": "Use parameterized queries or an ORM",
             "cwe_id": "CWE-89"
           }
         ]
       }
     ]
   }
   ```

2. **Update system prompt suffix** in `AIBackend._build_system_prompt()`:
   
   Append explicit JSON instructions:
   ```
   IMPORTANT: You MUST respond with valid JSON matching this schema:
   {schema_here}
   
   Do NOT include markdown code fences, preamble, or explanation.
   Return ONLY the JSON object. No markdown, no fences, no extra text.
   ```

3. **Update `_build_multi_file_user_message()`** in `base.py`:
   - Remove `=== FILE:` and `--- FINDING ---` delimiter instructions
   - Replace with: `"Respond with JSON following the schema above. Include all findings."`

4. **Update `_build_user_message()`** in `base.py`:
   - Same JSON schema instructions
   - Single-file path should populate `files[0]`

5. **Rewrite response parsing** — replace `_split_combined_feedback()` in `reviewer.py` with a new `_parse_structured_response()`:
   - Strategy 1: Try `json.loads(response)` directly
   - Strategy 2: Extract JSON from markdown code fences (`` ```json ... ``` ``)
   - Strategy 3: Fall back to existing regex delimiter parsing for backward compatibility
   - Log a warning when fallback is used

6. **Map JSON fields to `ReviewIssue`**:
   - `severity` → `ReviewIssue.severity`
   - `line` → `ReviewIssue.line_number`
   - `category` → `ReviewIssue.issue_type` (override/supplement review_type)
   - `title` + `description` → `ReviewIssue.description` (concat with separator)
   - `code_context` → `ReviewIssue.code_snippet`
   - Full JSON object → `ReviewIssue.ai_feedback`
   - `cwe_id`, `suggestion` → store in ai_feedback or new optional fields

7. **Deprecate but keep fallback**:
   - Keep `_parse_severity()` as a helper for fallback mode
   - Keep `_split_combined_feedback()` as legacy function
   - Document as deprecated in docstrings

### Config Change

No config changes required, but consider:
```ini
[processing]
response_format = json  # or "legacy" for backward compat fallback
```

---

## Part 3 — Adaptive Batch Sizing

**Addresses:** #3 (Batch Size Trade-off), #8 (Expensive Failure Recovery)

**Purpose:** Replace static batch size with intelligent batching based on token budget.

### Implementation Steps

1. **Create `_estimate_token_count(content: str) -> int`** in `reviewer.py`:
   - Simple heuristic: `len(content) // 4` (rough estimate)
   - Or: use `tiktoken` library if installed (optional dependency)
   - Fallback to character count heuristic if tiktoken not available

2. **Create `_build_adaptive_batches()`** function in `reviewer.py`:
   ```python
   def _build_adaptive_batches(
       target_files: Sequence[FileInfo],
       max_tokens_per_batch: int = 80000,
       max_files_per_batch: int = 10,
   ) -> List[List[FileInfo]]:
       """Group files into batches respecting token budget and file count limits."""
       batches = []
       current_batch = []
       current_tokens = 0
       
       # Sort by size descending so large files get their own batch
       sorted_files = sorted(
           target_files,
           key=lambda f: _estimate_token_count(
               f["content"] if isinstance(f, dict) else _read_file_content(f)
           ),
           reverse=True
       )
       
       for file_info in sorted_files:
           tokens = _estimate_token_count(...)
           
           # If this file alone exceeds budget, send individually
           if tokens > max_tokens_per_batch:
               if current_batch:
                   batches.append(current_batch)
                   current_batch = []
                   current_tokens = 0
               batches.append([file_info])
               continue
           
           # If adding this file exceeds budget or file count, start new batch
           if (current_tokens + tokens > max_tokens_per_batch or 
               len(current_batch) >= max_files_per_batch):
               if current_batch:
                   batches.append(current_batch)
               current_batch = [file_info]
               current_tokens = tokens
           else:
               current_batch.append(file_info)
               current_tokens += tokens
       
       if current_batch:
           batches.append(current_batch)
       
       return batches
   ```

3. **Track per-batch success/failure** — add to `collect_review_issues()`:
   - Keep a counter `failed_batches_count`
   - Implement circuit breaker: if a batch fails, halve the token budget for subsequent batches
   - Log when circuit breaker activates

4. **Add config options** to `src/aicodereviewer/config.py`:
   ```ini
   [processing]
   max_batch_token_budget = 80000
   batch_size = 10                        # hard cap on file count
   enable_adaptive_batching = true
   circuit_breaker_enabled = true
   ```

5. **Update `collect_review_issues()`** to use `_build_adaptive_batches()`:
   - Instead of: `batches = [target_files[i:i+batch_size] for i in range(...)]`
   - Use: `batches = _build_adaptive_batches(target_files, max_tokens, batch_size)`

---

## Part 4 — Cross-Issue Interaction Analysis

**Addresses:** #4 (Limited Cross-Issue Understanding)

**Purpose:** Add a second-pass analysis to detect interactions and conflicts between findings.

### Implementation Steps

1. **Add field to `ReviewIssue`** in `models.py`:
   ```python
   @dataclass
   class ReviewIssue:
       # ... existing fields ...
       related_issues: List[str] = field(default_factory=list)  # issue IDs
       interaction_summary: Optional[str] = None
   ```

2. **Create `_analyze_interactions()`** in `reviewer.py`:
   ```python
   def _analyze_interactions(
       issues: List[ReviewIssue],
       client: AIBackend,
       lang: str,
   ) -> List[ReviewIssue]:
       """Analyze relationships and conflicts between findings."""
       if not issues or len(issues) < 2:
           return issues
       
       # Build summary of all findings
       summary = []
       for i, issue in enumerate(issues):
           summary.append(f"[{i}] {issue.file_path}:{issue.line_number} "
                         f"({issue.severity}) {issue.issue_type}: {issue.description}")
       
       # Create interaction prompt
       interaction_prompt = (
           "Given these code review findings:\n\n"
           + "\n".join(summary) +
           "\n\nIdentify interactions between findings:\n"
           "- Which findings might conflict if both are fixed?\n"
           "- Does fixing one issue introduce another?\n"
           "- Are there cascade effects?\n"
           "- Which findings should be prioritized together?\n"
           "Respond as JSON with array of interactions."
       )
       
       # Get interaction analysis (use existing backend)
       response = client.get_review(
           interaction_prompt,
           review_type="interaction_analysis",
           lang=lang
       )
       
       # Parse and apply relationships...
       # Mark related issues with cross-references
       
       return issues
   ```

3. **Integrate into `collect_review_issues()`**:
   - After main review: `if enable_interaction_analysis: issues = _analyze_interactions(issues, client, lang)`

4. **Update `ReviewReport`** in `models.py`:
   ```python
   @dataclass
   class ReviewReport:
       # ... existing fields ...
       interaction_analysis: Optional[str] = None
   ```

5. **Update GUI** in `results_mixin.py`:
   - Show a "Related" badge on cards with `related_issues`
   - Tooltip shows the interaction summary

6. **Add config**:
   ```ini
   [processing]
   enable_interaction_analysis = false    # disabled by default (costs API call)
   ```

---

## Part 5 — Diff-Aware Review Mode

**Addresses:** #5 (No Historical or Behavioral Context)

**Purpose:** Enhance diff scope to include surrounding context and commit messages.

### Implementation Steps

1. **Enhance `parse_diff_file()`** in `scanner.py`:
   - Parse hunk headers (e.g., `@@ -10,5 +10,8 @@`) to extract function/class context
   - Capture N lines of surrounding unchanged context (default: 20 lines before/after)
   - Preserve diff markers: `+` for additions, `-` for removals
   - Return enhanced structure:
     ```python
     {
         "filename": "src/app.py",
         "changes": [
             {
                 "added": [list of added lines with line numbers],
                 "removed": [list of removed lines with line numbers],
                 "context_before": [20 lines before first change],
                 "context_after": [20 lines after last change],
                 "hunk_header": "@@ -42,10 +42,15 @@",
                 "function_name": "authenticate_user()",  # extracted from hunk header
             }
         ]
     }
     ```

2. **Create `_build_diff_user_message()`** in `base.py`:
   ```
   CHANGED FILE: src/app.py
   
   FUNCTION/CLASS CONTEXT: authenticate_user() [line 42]
   
   DIFF (added/removed lines):
   - user = db.query(User).filter_by(id=user_id)  # removed
   + user = db.query(User).filter_by(id=user_id).first()  # added
   
   SURROUNDING CONTEXT (unchanged code):
   [20 lines before]
   [20 lines after]
   
   FOCUS YOUR REVIEW ON THE CHANGED LINES.
   Use surrounding context only to understand intent and impact.
   ```

3. **Enhance `collect_review_issues()`** to detect diff mode:
   - When `file_info` is a dict with `"content"` (from diff parsing), use diff-aware builder
   - Pass `use_diff_mode=True` flag through the call chain

4. **Add commit message context** when commits are specified:
   - Run: `git log --format=%B <commit_range>`
   - Capture commit message(s)
   - Include in prompt as:
     ```
     COMMIT MESSAGE:
     <message>
     
     ---
     [rest of review prompt]
     ```

5. **Update `scanner.py`'s `get_diff_from_commits()`** to also return commit messages:
   ```python
   def get_diff_and_messages(project_path: str, commit_range: str) -> Tuple[Optional[str], Optional[str]]:
       """Return both diff content and commit messages."""
       # ... existing diff logic ...
       # Also run: git log --format=%B <range> > messages
       return diff_content, messages
   ```

6. **Add config**:
   ```ini
   [processing]
   diff_context_lines = 20
   include_commit_messages = true
   ```

---

## Part 6 — Robust Response Parser with Validation

**Addresses:** #2 (Delimiter Parsing), #6 (Severity Extraction) — provides hardening layer

**Purpose:** Build a multi-strategy parser that tries structured first, then falls back gracefully.

### Implementation Steps

1. **Create new file** `src/aicodereviewer/response_parser.py`:
   ```python
   """Parse AI review responses using multiple strategies with fallback."""
   
   from typing import List, Optional, Dict, Any
   from .models import ReviewIssue
   
   def parse_review_response(
       response: str,
       file_entries: List[Dict[str, Any]],
       review_type: str,
   ) -> List[ReviewIssue]:
       """Parse review response using strategy chain."""
       strategies = [
           _try_json_parse,
           _try_markdown_json_parse,
           _try_delimiter_parse,
           _try_heuristic_parse,
       ]
       
       for strategy in strategies:
           try:
               issues = strategy(response, file_entries, review_type)
               if issues:
                   logger.info(f"✓ Parsed with {strategy.__name__}")
                   return issues
           except Exception as e:
               logger.debug(f"Strategy {strategy.__name__} failed: {e}")
               continue
       
       # Ultimate fallback: one generic issue per file
       logger.warning("All parsing strategies failed, creating generic issues")
       return _create_generic_issues(file_entries, response, review_type)
   
   
   def _try_json_parse(...) -> List[ReviewIssue]:
       """Strategy 1: Parse as raw JSON (from Part 2)."""
       data = json.loads(response)
       return _json_to_issues(data)
   
   
   def _try_markdown_json_parse(...) -> List[ReviewIssue]:
       """Strategy 2: Extract JSON from markdown code fences."""
       match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
       if match:
           data = json.loads(match.group(1))
           return _json_to_issues(data)
       raise ValueError("No JSON code block found")
   
   
   def _try_delimiter_parse(...) -> List[ReviewIssue]:
       """Strategy 3: Original === FILE: / --- FINDING --- parsing (backward compat)."""
       # Call the existing _split_combined_feedback logic
       return _split_combined_feedback(response, file_entries, review_type)
   
   
   def _try_heuristic_parse(...) -> List[ReviewIssue]:
       """Strategy 4: Line-by-line heuristic parsing."""
       # Split response into lines
       # Look for severity keywords at line start
       # Group related lines into issues
       # Extract line numbers from "line NN" patterns
       # ...
   
   
   def _normalize_severity(severity_str: str) -> str:
       """Normalize severity through strict allowlist."""
       severity_map = {
           "critical": "critical",
           "crit": "critical",
           "high": "high",
           "severe": "high",
           "medium": "medium",
           "med": "medium",
           "low": "low",
           "minor": "low",
           "info": "info",
           "informational": "info",
       }
       normalized = severity_map.get(severity_str.lower().strip())
       if not normalized:
           logger.warning(f"Unknown severity '{severity_str}', defaulting to 'medium'")
           return "medium"
       return normalized
   
   
   def _extract_line_number(text: str) -> Optional[int]:
       """Extract line number from patterns like 'line 42', 'L42', ':42:'."""
       patterns = [
           r'(?:line|at)\s+(\d+)',
           r'(?::)?(\d+):',
           r'L(\d+)',
       ]
       for pattern in patterns:
           match = re.search(pattern, text)
           if match:
               return int(match.group(1))
       return None
   
   
   def _deduplicate_issues(issues: List[ReviewIssue]) -> List[ReviewIssue]:
       """Detect and merge near-duplicate findings (same file + similar description)."""
       # Use simple token overlap (cosine similarity on description words)
       # Merge if overlap > 70%
       # Keep the more detailed version
       # ...
   ```

2. **Wire into `reviewer.py`**:
   - Replace: `issues = _split_combined_feedback(feedback, file_entries, review_type)`
   - With: `issues = parse_review_response(feedback, file_entries, review_type)`

3. **Add unit tests** in `tests/test_response_parser.py`:
   - Test each strategy with well-formatted, partially formatted, and unformatted responses
   - Test severity normalization
   - Test line number extraction
   - Test deduplication

4. **Logging**:
   - Log which strategy succeeded
   - Log warnings when unknown severities or formats encountered
   - Log when deduplication merges issues

---

## Part 7 — Project Type Detection and Prompt Tuning

**Addresses:** #7 (No Project Type Awareness)

**Purpose:** Extend Part 1 to automatically tailor prompts based on detected framework.

### Implementation Steps

1. **Expand `context_collector.py`** (Part 1) to detect:
   - Web frameworks: Django, Flask, FastAPI, Express, Next.js, Spring Boot, Rails
   - Testing: pytest, jest, JUnit, unittest
   - Linting/formatting: eslint, ruff, black, prettier, flake8
   - CI/CD: GitHub Actions, GitLab CI, Jenkins
   - Package managers: pip, npm, cargo, gradle

2. **Create `FRAMEWORK_PROMPT_SUPPLEMENTS`** dict in `base.py`:
   ```python
   FRAMEWORK_PROMPT_SUPPLEMENTS = {
       "django": (
           "This is a Django project. Pay special attention to:\n"
           "- ORM N+1 query patterns (use select_related/prefetch_related)\n"
           "- CSRF middleware and token handling\n"
           "- QuerySet lazy evaluation and caching\n"
           "- Template injection and XSS vulnerabilities\n"
           "- Middleware execution order"
       ),
       "fastapi": (
           "This is a FastAPI project. Pay special attention to:\n"
           "- Pydantic model validation and coercion\n"
           "- Async/await correctness (no blocking calls)\n"
           "- Dependency injection resolution\n"
           "- Request/response serialization\n"
           "- Background task execution"
       ),
       "react": (
           "This is a React project. Pay special attention to:\n"
           "- React Hook rules (dependencies array completeness)\n"
           "- Memory leaks from uncleared intervals/listeners\n"
           "- Unnecessary re-renders and useCallback/useMemo\n"
           "- Stale closures in event handlers\n"
           "- Prop drilling that should use Context"
       ),
       # ... more frameworks
   }
   ```

3. **Detect frameworks in `context_collector.py`**:
   - Check for framework-specific files, imports, configuration
   - Return detected frameworks as list

4. **Auto-append supplements** in `_build_system_prompt()`:
   ```python
   def _build_system_prompt(review_type: str, lang: str, detected_frameworks: List[str] = None) -> str:
       # ... existing logic ...
       base = REVIEW_PROMPTS.get(review_type, ...)
       
       if detected_frameworks:
           supplements = []
           for fw in detected_frameworks:
               if fw in FRAMEWORK_PROMPT_SUPPLEMENTS:
                   supplements.append(FRAMEWORK_PROMPT_SUPPLEMENTS[fw])
           if supplements:
               base += "\n\n" + "FRAMEWORK-SPECIFIC GUIDANCE:\n" + "\n\n".join(supplements)
       
       return base + lang_inst
   ```

5. **Thread frameworks through call chain**:
   - `collect_review_issues()` → get from context_collector
   - `_process_file_batch()` → pass to `get_review()`
   - `get_review()` → pass to `_build_system_prompt()`

6. **Add config override** in `config.py`:
   ```ini
   [processing]
   detected_frameworks =        # comma-separated; override auto-detection
   ```

---

## Part 8 — Smart Retry with Budget Tracking

**Addresses:** #8 (Expensive Failure Recovery)

**Purpose:** Replace "retry entire batch individually" with intelligent, budget-aware recovery.

### Implementation Steps

1. **Create `_ReviewSession` dataclass** in `reviewer.py`:
   ```python
   @dataclass
   class _ReviewSession:
       """Track API usage and budget across a review session."""
       total_api_calls: int = 0
       total_tokens_sent: int = 0
       estimated_tokens_received: int = 0
       failed_batches: int = 0
       successful_batches: int = 0
       budget_limit: int = 0
       
       def remaining_budget(self) -> bool:
           """Check if we can make more API calls."""
           return (self.total_api_calls < self.budget_limit or 
                   self.budget_limit == 0)  # 0 = unlimited
       
       def estimated_total_tokens(self) -> int:
           return self.total_tokens_sent + self.estimated_tokens_received
   ```

2. **Create `_retry_with_backoff()`** function:
   ```python
   def _retry_with_backoff(
       batch: List[FileInfo],
       review_type: str,
       client: AIBackend,
       lang: str,
       spec_content: Optional[str],
       session: _ReviewSession,
       cancel_check: Optional[CancelCheck],
   ) -> List[ReviewIssue]:
       """Retry a failed batch once with simplified prompt before fallback."""
       logger.warning(f"Retrying batch with {len(batch)} files...")
       
       try:
           # Try once more with same parameters
           issues = _process_combined_batch(batch, review_type, client, lang, spec_content, cancel_check)
           session.successful_batches += 1
           return issues
       except Exception as e:
           logger.error(f"Retry failed: {e}. Falling back to individual.")
           session.failed_batches += 1
           
           # Check budget before falling back
           if not session.remaining_budget():
               logger.warning("Budget exhausted; skipping remaining files")
               return []
           
           # Fall back to individual file processing
           return _process_files_individually(batch, review_type, client, lang, spec_content, cancel_check)
   ```

3. **Update batch processing loop** in `collect_review_issues()`:
   ```python
   session = _ReviewSession(budget_limit=config.get("performance", "max_api_calls_per_session", 50))
   
   for batch in batches:
       if not session.remaining_budget():
           logger.warning(f"Budget limit reached; skipping {len(batches)-done} remaining batches")
           break
       
       try:
           batch_issues = _process_file_batch(batch, combined_type, client, lang, spec_content, cancel_check)
           issues.extend(batch_issues)
           session.total_api_calls += 1
           session.successful_batches += 1
       except Exception as e:
           session.failed_batches += 1
           batch_issues = _retry_with_backoff(batch, combined_type, client, lang, spec_content, session, cancel_check)
           issues.extend(batch_issues)
           session.total_api_calls += 1
   ```

4. **Add config**:
   ```ini
   [performance]
   max_api_calls_per_session = 50
   warn_on_budget_exhaustion = true
   ```

5. **Surface in GUI**:
   - Show estimated token usage and API call count in status bar
   - Update `results_mixin.py` to display: `"Status: Used 12/50 API calls (15,234/80,000 tokens)"`

---

## Part 9 — File Content Cache with Staleness Detection

**Addresses:** #9 (Cache Invalidation Issues)

**Purpose:** Replace simple `_BoundedCache` with mtime-aware caching and invalidation.

### Implementation Steps

1. **Extend cache in `reviewer.py`**:
   ```python
   class _BoundedCache:
       """Cache with staleness detection via mtime."""
       
       def __init__(self, maxsize: int = 100):
           self._data: OrderedDict[str, Tuple[str, float, int]] = OrderedDict()
           # Format: key -> (content, mtime, file_size)
           self.maxsize = maxsize
           self._lock = threading.Lock()
       
       def get(self, key: str) -> Optional[str]:
           with self._lock:
               if key not in self._data:
                   return None
               
               content, cached_mtime, cached_size = self._data[key]
               
               # Check if file has changed
               try:
                   actual_mtime = os.path.getmtime(key)
                   actual_size = os.path.getsize(key)
                   
                   if actual_mtime != cached_mtime or actual_size != cached_size:
                       logger.debug(f"Cache stale for {key}, invalidating")
                       del self._data[key]
                       return None
               except (OSError, FileNotFoundError):
                   # File deleted, remove from cache
                   del self._data[key]
                   return None
               
               # Valid cache hit
               self._data.move_to_end(key)
               return content
       
       def put(self, key: str, value: str) -> None:
           with self._lock:
               try:
                   mtime = os.path.getmtime(key)
                   size = os.path.getsize(key)
               except (OSError, FileNotFoundError):
                   mtime = time.time()
                   size = len(value)
               
               if key in self._data:
                   self._data.move_to_end(key)
               else:
                   if len(self._data) >= self.maxsize:
                       self._data.popitem(last=False)
               
               self._data[key] = (value, mtime, size)
       
       def invalidate_path(self, path: str) -> None:
           """Invalidate a specific file path."""
           with self._lock:
               if path in self._data:
                   del self._data[path]
       
       def clear(self) -> None:
           """Clear entire cache."""
           with self._lock:
               self._data.clear()
   ```

2. **Thread safety** — the lock ensures concurrent reads from parallel processing don't corrupt state

3. **Update clear_file_cache()** to expose invalidation:
   ```python
   def clear_file_cache() -> None:
       """Clear the file-content cache."""
       _file_content_cache.clear()
   
   def invalidate_file_cache(path: str) -> None:
       """Invalidate a specific file in the cache."""
       _file_content_cache.invalidate_path(str(path))
   ```

4. **Wire into GUI editor** in `results_mixin.py`:
   ```python
   def _open_builtin_editor(self, idx: int, ...):
       # ... existing editor code ...
       
       def _save() -> None:
           # ... write file ...
           issue.status = "resolved"
           # Invalidate cache so next review sees new content
           invalidate_file_cache(issue.file_path)
           self._refresh_status(idx)
           # ... rest of save logic ...
   ```

---

## Part 10 — Cross-File Architectural Analysis Pass

**Addresses:** #10 (Cannot Flag Architectural Smells)

**Purpose:** Add optional second-pass review at project level for architecture issues.

### Implementation Steps

1. **Create `_architectural_review()`** in `reviewer.py`:
   ```python
   def _architectural_review(
       files: Sequence[FileInfo],
       all_issues: List[ReviewIssue],
       client: AIBackend,
       lang: str,
   ) -> Optional[str]:
       """Perform project-level architectural review."""
       if not files or len(files) < 3:
           logger.debug("Skipping architectural review (too few files)")
           return None
       
       # Build project structure summary
       structure_summary = _build_project_structure_summary(files)
       
       # Build findings summary
       findings_summary = "\n".join([
           f"- {iss.file_path}: {iss.issue_type} ({iss.severity})"
           for iss in all_issues[:50]  # Limit to top 50
       ])
       
       # Build architectural prompt
       arch_prompt = (
           "Analyze this project structure for architectural issues:\n\n"
           + structure_summary +
           "\n\nExisting findings:\n" + findings_summary +
           "\n\nIdentify architectural issues:\n"
           "- Circular dependencies\n"
           "- Layering violations\n"
           "- God classes/modules (overly large files)\n"
           "- Inappropriate coupling\n"
           "- Missing abstractions\n"
           "- Single points of failure\n"
           "- Incoherent module organization\n"
           "\nRespond with identified issues and recommendations."
       )
       
       logger.info("Running architectural review...")
       response = client.get_review(
           arch_prompt,
           review_type="architecture",
           lang=lang
       )
       
       return response
   ```

2. **Create helper to build project structure summary**:
   ```python
   def _build_project_structure_summary(files: Sequence[FileInfo]) -> str:
       """Build a concise project structure description."""
       # Count files by type
       file_types = {}
       for file_info in files:
           if isinstance(file_info, dict):
               fname = file_info["filename"]
           else:
               fname = str(file_info)
           
           ext = Path(fname).suffix
           file_types[ext] = file_types.get(ext, 0) + 1
       
       # Build file list by directory
       dirs = {}
       for file_info in files:
           if isinstance(file_info, dict):
               path = file_info["filename"]
           else:
               path = str(file_info)
           
           dir_path = str(Path(path).parent)
           if dir_path not in dirs:
               dirs[dir_path] = []
           dirs[dir_path].append(Path(path).name)
       
       # Format summary
       summary = "Project Structure:\n"
       for dir_path in sorted(dirs.keys())[:10]:  # Top 10 dirs
           summary += f"\n{dir_path}/\n"
           for file_name in sorted(dirs[dir_path])[:5]:  # Top 5 files per dir
               summary += f"  - {file_name}\n"
       
       summary += f"\nFile types: {file_types}\n"
       return summary
   ```

3. **Integrate into `collect_review_issues()`**:
   ```python
   issues = collect_review_issues(...)  # existing logic
   
   if config.get("processing", "enable_architectural_review", False):
       arch_feedback = _architectural_review(target_files, issues, client, lang)
       if arch_feedback:
           # Parse architectural findings and add to issues
           arch_issues = parse_review_response(
               arch_feedback,
               [{"name": "PROJECT", "path": "", "content": ""}],
               "architecture"
           )
           issues.extend(arch_issues)
   
   return issues
   ```

4. **Update `ReviewReport`** in `models.py`:
   ```python
   @dataclass
   class ReviewReport:
       # ... existing fields ...
       architecture_summary: Optional[str] = None
   ```

5. **Add to `ReviewReport.to_dict()` / `from_dict()`** for serialization

6. **Make opt-in in config**:
   ```ini
   [processing]
   enable_architectural_review = false
   architecture_summary_max_tokens = 5000
   ```

7. **Add toggle to GUI** — checkbox in Review tab: "Include architectural analysis"

---

## Implementation Priority & Dependencies

| Priority | Part | Effort | Dependencies |
|----------|------|--------|-------------|
| **P0** | Part 2 — Structured JSON Output | Medium | None |
| **P0** | Part 6 — Robust Response Parser | Medium | Part 2 |
| **P1** | Part 1 — Project Context Collector | Medium | None |
| **P1** | Part 5 — Diff-Aware Review | Medium | None |
| **P1** | Part 9 — Cache Staleness Detection | Small | None |
| **P2** | Part 3 — Adaptive Batch Sizing | Medium | None |
| **P2** | Part 8 — Smart Retry + Budget | Medium | Part 3 |
| **P2** | Part 7 — Project Type Prompt Tuning | Small | Part 1 |
| **P3** | Part 4 — Cross-Issue Interaction | Medium | Part 2 |
| **P3** | Part 10 — Architectural Analysis | Large | Part 1 |

**P0 = Reliability fixes**  
**P1 = High-value context additions**  
**P2 = Efficiency improvements**  
**P3 = Advanced analysis features**

---

## Files Modified Per Part

| Part | New Files | Modified Files |
|------|-----------|----------------|
| 1 | `context_collector.py` | `reviewer.py`, `base.py`, `config.py` |
| 2 | — | `base.py`, `reviewer.py` |
| 3 | — | `reviewer.py`, `config.py` |
| 4 | — | `reviewer.py`, `models.py`, `results_mixin.py` |
| 5 | — | `scanner.py`, `base.py`, `reviewer.py`, `config.py` |
| 6 | `response_parser.py` | `reviewer.py` |
| 7 | — | `context_collector.py`, `base.py`, `config.py` |
| 8 | — | `reviewer.py`, `config.py`, `results_mixin.py` |
| 9 | — | `reviewer.py`, `results_mixin.py` |
| 10 | — | `reviewer.py`, `models.py`, `context_collector.py`, `config.py` |

---

## Testing Strategy

For each part, create tests in `tests/`:
- Unit tests for new functions (token estimation, context building, response parsing)
- Integration tests for call chain threading
- Mock tests for API responses (well-formatted, edge cases, failures)
- GUI tests for new UI elements

---

## Rollout Plan

1. **Phase 1 (P0 items, weeks 1-2)**: Part 2 + Part 6
   - Single most impactful change: JSON output + robust parser
   - Improves reliability immediately

2. **Phase 2 (P1 items, weeks 3-4)**: Part 1 + Part 5 + Part 9
   - Add project context
   - Add diff awareness
   - Fix cache invalidation

3. **Phase 3 (P2 items, weeks 5-6)**: Part 3 + Part 8 + Part 7
   - Smarter batching
   - Budget tracking
   - Framework-specific guidance

4. **Phase 4 (P3 items, weeks 7-8)**: Part 4 + Part 10
   - Cross-issue analysis
   - Architectural review

---

## Success Metrics

- **Reliability**: 95%+ parse success rate (vs. ~85% currently with delimiters)
- **Efficiency**: 40% fewer API calls per session with adaptive batching
- **Context**: Prompt length increase ~20% from project context (acceptable)
- **Latency**: Architectural pass adds <1 min for medium projects
- **User feedback**: Fewer "weird results" reports from isolated file analysis
