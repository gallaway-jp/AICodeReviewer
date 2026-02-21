# src/aicodereviewer/gui/test_fixtures.py
"""
Sample data fixtures for the GUI manual testing mode.

Provides factory functions that generate realistic :class:`ReviewIssue`
objects covering every severity, status, and UI state the Results tab
can display.  The fixtures are deliberately **data-driven** so that
future additions to ``ReviewIssue`` fields, severity levels, or status
values only require updates here (single place), keeping the manual
test mode resilient to GUI refactors.
"""
from datetime import datetime, timedelta
from typing import Dict, List

from aicodereviewer.models import ReviewIssue

# ── severity × status matrix ──────────────────────────────────────────────
# Every combination a reviewer might encounter in a real session.

_ISSUE_TEMPLATES: List[Dict[str, object]] = [
    # ── critical ───────────────────────────────────────────────────────────
    {
        "file_path": "src/auth/login.py",
        "line_number": 42,
        "issue_type": "security",
        "severity": "critical",
        "description": (
            "SQL injection via unsanitised user input in login query. "
            "The username parameter is concatenated directly into the SQL string "
            "without parameterised queries or escaping, allowing an attacker to "
            "bypass authentication or exfiltrate the entire users table."
        ),
        "code_snippet": (
            "def authenticate(user, password):\n"
            "    query = f\"SELECT * FROM users WHERE name='{user}'\"\n"
            "    cursor.execute(query)\n"
        ),
        "ai_feedback": (
            "The login query concatenates user input directly into SQL. "
            "An attacker can inject arbitrary SQL such as `' OR 1=1 --`. "
            "Use parameterised queries: `cursor.execute(\"SELECT ... WHERE "
            "name = %s\", (user,))`."
        ),
        "status": "pending",
    },
    # ── high / resolved ────────────────────────────────────────────────────
    {
        "file_path": "src/api/handlers.py",
        "line_number": 118,
        "issue_type": "error_handling",
        "severity": "high",
        "description": "Bare except clause swallows all exceptions silently",
        "code_snippet": (
            "try:\n"
            "    response = api_client.post(url, data=payload)\n"
            "except:\n"
            "    pass\n"
        ),
        "ai_feedback": (
            "A bare `except:` will catch everything including "
            "`KeyboardInterrupt` and `SystemExit`. Catch `Exception` at "
            "minimum and log the error."
        ),
        "status": "resolved",
        "resolved_at": datetime.now() - timedelta(minutes=5),
    },
    # ── high / pending ─────────────────────────────────────────────────────
    {
        "file_path": "src/core/engine.py",
        "line_number": 256,
        "issue_type": "performance",
        "severity": "high",
        "description": "Nested loop causes O(n²) complexity on large datasets",
        "code_snippet": (
            "for item in dataset:\n"
            "    for other in dataset:\n"
            "        if item.id == other.parent_id:\n"
            "            item.children.append(other)\n"
        ),
        "ai_feedback": (
            "Build a lookup dict keyed by `parent_id` in one pass, then "
            "iterate once to attach children. This reduces the complexity "
            "from O(n²) to O(n)."
        ),
        "status": "pending",
    },
    # ── medium / skipped ───────────────────────────────────────────────────
    {
        "file_path": "src/utils/helpers.py",
        "line_number": 33,
        "issue_type": "code_quality",
        "severity": "medium",
        "description": "Magic number 86400 used without named constant",
        "code_snippet": (
            "def cache_ttl():\n"
            "    return time.time() + 86400\n"
        ),
        "ai_feedback": (
            "Replace `86400` with a named constant like "
            "`SECONDS_PER_DAY = 86_400` for readability."
        ),
        "status": "skipped",
        "resolution_reason": "Intentional — matches upstream API contract",
    },
    # ── medium / ai_fixed ──────────────────────────────────────────────────
    {
        "file_path": "src/models/user.py",
        "line_number": 77,
        "issue_type": "security",
        "severity": "medium",
        "description": "Password stored in plain text in User model",
        "code_snippet": (
            "class User:\n"
            "    def __init__(self, name, password):\n"
            "        self.name = name\n"
            "        self.password = password\n"
        ),
        "ai_feedback": (
            "Passwords must be hashed before storage. Use `bcrypt` or "
            "`argon2-cffi` to hash on creation and verify during login."
        ),
        "status": "ai_fixed",
        "ai_fix_applied": (
            "import bcrypt\n\n"
            "class User:\n"
            "    def __init__(self, name, password):\n"
            "        self.name = name\n"
            "        self.password_hash = bcrypt.hashpw(\n"
            "            password.encode(), bcrypt.gensalt()\n"
            "        )\n"
        ),
    },
    # ── low / pending ──────────────────────────────────────────────────────
    {
        "file_path": "src/api/routes.py",
        "line_number": 5,
        "issue_type": "code_quality",
        "severity": "low",
        "description": "Unused import 'os' at top of module",
        "code_snippet": (
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
        ),
        "ai_feedback": (
            "The `os` module is imported but never used in this file. "
            "Remove the unused import to keep the module clean."
        ),
        "status": "pending",
    },
    # ── low / fix_failed ───────────────────────────────────────────────────
    {
        "file_path": "src/core/pipeline.py",
        "line_number": 189,
        "issue_type": "error_handling",
        "severity": "low",
        "description": "Return value of subprocess.run() is not checked",
        "code_snippet": (
            "def run_lint(path):\n"
            "    subprocess.run(['flake8', str(path)])\n"
        ),
        "ai_feedback": (
            "Use `check=True` or inspect `.returncode` to detect lint "
            "failures. Silently ignoring errors may mask problems."
        ),
        "status": "fix_failed",
        "resolved_at": datetime.now() - timedelta(minutes=2),
    },
    # ── info / pending ─────────────────────────────────────────────────────
    {
        "file_path": "README.md",
        "line_number": None,
        "issue_type": "documentation",
        "severity": "info",
        "description": "README lacks installation instructions for contributors",
        "code_snippet": (
            "# MyProject\n\n"
            "A tool for analysing code quality.\n"
        ),
        "ai_feedback": (
            "Add a 'Getting Started' section with `pip install -e .[dev]` "
            "and any prerequisite tools."
        ),
        "status": "pending",
    },
    # ── info / resolved ────────────────────────────────────────────────────
    {
        "file_path": "tests/conftest.py",
        "line_number": 12,
        "issue_type": "code_quality",
        "severity": "info",
        "description": "Consider adding type hints to test fixtures",
        "code_snippet": (
            "@pytest.fixture\n"
            "def sample_user():\n"
            "    return {'name': 'alice', 'role': 'admin'}\n"
        ),
        "ai_feedback": (
            "Adding return type annotations `-> Dict[str, str]` improves "
            "IDE support and documentation."
        ),
        "status": "resolved",
        "resolved_at": datetime.now() - timedelta(minutes=10),
    },
    # ── medium / pending (another for bulk) ────────────────────────────────
    {
        "file_path": "src/db/connection.py",
        "line_number": 45,
        "issue_type": "performance",
        "severity": "medium",
        "description": "Database connection created on every request instead of pooling",
        "code_snippet": (
            "def get_data(query):\n"
            "    conn = sqlite3.connect('app.db')\n"
            "    result = conn.execute(query).fetchall()\n"
            "    conn.close()\n"
            "    return result\n"
        ),
        "ai_feedback": (
            "Creating a new connection for every request adds latency. "
            "Use a connection pool (e.g. `sqlite3` with a module-level "
            "connection, or `sqlalchemy.pool`)."
        ),
        "status": "pending",
    },
]

# ── Public API ─────────────────────────────────────────────────────────────


def create_sample_issues() -> List[ReviewIssue]:
    """Return a list of sample :class:`ReviewIssue` objects.

    Covers every severity (critical → info) and every status
    (pending, resolved, skipped, ai_fixed, fix_failed).

    The data is intentionally created via the dataclass constructor
    so that if ``ReviewIssue`` gains new required fields the test
    fixtures will fail loudly at import time rather than silently
    producing broken UI.
    """
    issues: List[ReviewIssue] = []
    for tmpl in _ISSUE_TEMPLATES:
        issues.append(ReviewIssue(**tmpl))  # type: ignore[arg-type]
    return issues


def apply_test_config() -> None:
    """Overwrite the global :data:`config` singleton with test-specific values.

    This sets recognisable non-default values so the tester can verify
    that the Settings tab is reading from the isolated test config
    rather than the real ``config.ini``.  Settings are applied via
    ``set_value`` (runtime-only) so the real file is **never touched**.
    """
    from aicodereviewer.config import config

    # ── Backend ────────────────────────────────────────────────────────────
    config.set_value("backend", "type", "local")

    # ── AWS (recognisable dummy values) ────────────────────────────────────
    config.set_value("aws", "region", "ap-northeast-1")
    config.set_value("aws", "sso_session", "test-sso-session")
    config.set_value("aws", "access_key_id", "AKIAIOSFODNN7EXAMPLE")
    config.set_value("model", "model_id",
                     "anthropic.claude-3-5-sonnet-20240620-v1:0")

    # ── Kiro ───────────────────────────────────────────────────────────────
    config.set_value("kiro", "wsl_distro", "Ubuntu-22.04")
    config.set_value("kiro", "cli_command", "kiro")
    config.set_value("kiro", "timeout", "120")

    # ── Copilot ────────────────────────────────────────────────────────────
    config.set_value("copilot", "copilot_path", "copilot")
    config.set_value("copilot", "timeout", "180")
    config.set_value("copilot", "model", "gpt-4o")

    # ── Local LLM ──────────────────────────────────────────────────────────
    config.set_value("local_llm", "api_url", "http://localhost:1234")
    config.set_value("local_llm", "api_type", "lmstudio")
    config.set_value("local_llm", "model", "qwen2.5-coder-14b")
    config.set_value("local_llm", "api_key", "test-api-key-12345")
    config.set_value("local_llm", "timeout", "600")
    config.set_value("local_llm", "max_tokens", "8192")

    # ── Performance (slightly different from defaults) ─────────────────────
    config.set_value("performance", "max_requests_per_minute", "20")
    config.set_value("performance", "min_request_interval_seconds", "3.0")
    config.set_value("performance", "max_file_size_mb", "20")
    config.set_value("processing", "batch_size", "10")
    config.set_value("processing", "combine_files", "false")

    # ── GUI ────────────────────────────────────────────────────────────────
    config.set_value("gui", "theme", "dark")
    config.set_value("gui", "language", "en")
    config.set_value("gui", "review_language", "en")
    config.set_value("gui", "editor_command", "")
    config.set_value("gui", "programmers", "Alice, Bob")
    config.set_value("gui", "reviewers", "Charlie")
    config.set_value("gui", "project_path", "C:/Projects/sample-app")
    config.set_value("gui", "spec_file", "review_spec.md")

    # ── Output formats ─────────────────────────────────────────────────────
    config.set_value("output", "formats", "json,txt,md")

    # ── Redirect save() to a temp file so the real config is never touched ─
    import tempfile
    _tmp = tempfile.NamedTemporaryFile(
        prefix="aicr_test_", suffix=".ini", delete=False
    )
    _tmp.close()
    config.config_path = __import__("pathlib").Path(_tmp.name)
