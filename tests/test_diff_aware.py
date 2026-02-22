# tests/test_diff_aware.py
"""Tests for Part 5 — Diff-Aware Review.

Covers:
- Enhanced diff parser (parse_diff_file_enhanced)
- DiffHunk / EnhancedDiffFile data structures
- Function-name extraction from hunk headers
- Commit-message retrieval (get_commit_messages)
- Diff-aware prompt builders (_build_diff_user_message, _build_multi_file_diff_user_message)
- Diff-mode detection in reviewer (_is_diff_entry)
- scan_project_with_scope enhanced output
"""
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aicodereviewer.scanner import (
    DiffHunk,
    EnhancedDiffFile,
    get_commit_messages,
    parse_diff_file,
    parse_diff_file_enhanced,
    _extract_function_from_hunk_ctx,
)
from aicodereviewer.backends.base import AIBackend
from aicodereviewer.reviewer import _is_diff_entry


# ── _extract_function_from_hunk_ctx ──────────────────────────────────────

class TestExtractFunctionFromHunkCtx:
    """Unit tests for extracting function/class names from hunk headers."""

    def test_python_def(self):
        result = _extract_function_from_hunk_ctx("def authenticate_user():")
        assert result is not None
        assert "authenticate_user" in result

    def test_python_async_def(self):
        result = _extract_function_from_hunk_ctx("async def fetch_data(url):")
        assert result is not None
        assert "fetch_data" in result

    def test_python_class(self):
        result = _extract_function_from_hunk_ctx("class UserManager:")
        assert result is not None
        assert "UserManager" in result

    def test_js_function(self):
        result = _extract_function_from_hunk_ctx("function handleClick(event)")
        assert result is not None
        assert "handleClick" in result

    def test_js_const_arrow(self):
        result = _extract_function_from_hunk_ctx("const processData = async (items) =>")
        assert result is not None
        assert "processData" in result

    def test_java_method(self):
        result = _extract_function_from_hunk_ctx("public void processRequest(HttpRequest req)")
        assert result is not None
        assert "processRequest" in result

    def test_empty_string(self):
        assert _extract_function_from_hunk_ctx("") is None

    def test_short_string(self):
        assert _extract_function_from_hunk_ctx("x") is None

    def test_plain_context(self):
        # Something that doesn't match known patterns but is long enough
        result = _extract_function_from_hunk_ctx("some random context text here")
        # Should return the raw string as fallback
        assert result is not None


# ── parse_diff_file_enhanced ─────────────────────────────────────────────

class TestParseDiffFileEnhanced:
    """Tests for the enhanced diff parser."""

    SIMPLE_DIFF = textwrap.dedent("""\
        --- a/app.py
        +++ b/app.py
        @@ -10,5 +10,6 @@ def authenticate_user():
             user = db.query(User).filter_by(id=user_id)
             if user is None:
                 return None
        -    return user
        +    return user.first()
        +    # Added .first() call
    """)

    def test_single_file_basic(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        assert len(result) == 1
        edf = result[0]
        assert edf.filename == "app.py"
        assert isinstance(edf, EnhancedDiffFile)

    def test_hunks_parsed(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        edf = result[0]
        assert len(edf.hunks) == 1
        hunk = edf.hunks[0]
        assert hunk.old_start == 10
        assert hunk.new_start == 10

    def test_function_name_extracted(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        hunk = result[0].hunks[0]
        assert hunk.function_name is not None
        assert "authenticate_user" in hunk.function_name

    def test_added_lines(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        hunk = result[0].hunks[0]
        added_texts = [t for _, t in hunk.added]
        assert any(".first()" in t for t in added_texts)

    def test_removed_lines(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        hunk = result[0].hunks[0]
        removed_texts = [t for _, t in hunk.removed]
        assert any("return user" in t for t in removed_texts)

    def test_context_before(self):
        result = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        hunk = result[0].hunks[0]
        # The 3 context lines before the change
        assert len(hunk.context_before) > 0
        ctx_text = "\n".join(hunk.context_before)
        assert "db.query" in ctx_text or "user" in ctx_text.lower()

    def test_backward_compatible_content(self):
        """content field should match parse_diff_file output."""
        legacy = parse_diff_file(self.SIMPLE_DIFF)
        enhanced = parse_diff_file_enhanced(self.SIMPLE_DIFF)
        assert len(legacy) == len(enhanced)
        assert legacy[0]["content"] == enhanced[0].content

    def test_multiple_files(self):
        diff = textwrap.dedent("""\
            --- a/file1.py
            +++ b/file1.py
            @@ -1,2 +1,3 @@
             print("hello")
            +print("world")
            --- a/file2.py
            +++ b/file2.py
            @@ -5,3 +5,4 @@ class Foo:
                 pass
            +    return True
        """)
        result = parse_diff_file_enhanced(diff)
        assert len(result) == 2
        filenames = [r.filename for r in result]
        assert "file1.py" in filenames
        assert "file2.py" in filenames

    def test_multiple_hunks_single_file(self):
        diff = textwrap.dedent("""\
            --- a/app.py
            +++ b/app.py
            @@ -1,3 +1,4 @@ def func_a():
                 pass
            +    return 1
            @@ -20,3 +21,4 @@ def func_b():
                 pass
            +    return 2
        """)
        result = parse_diff_file_enhanced(diff)
        assert len(result) == 1
        assert len(result[0].hunks) == 2
        assert result[0].hunks[0].function_name is not None
        assert result[0].hunks[1].function_name is not None

    def test_empty_diff(self):
        assert parse_diff_file_enhanced("") == []

    def test_context_lines_limit(self):
        """Pre-change context should be capped to context_lines param."""
        # Build a diff with many context lines
        context = "\n".join(f" line{i}" for i in range(50))
        diff = f"--- a/big.py\n+++ b/big.py\n@@ -1,55 +1,56 @@\n{context}\n+added_line\n"
        result = parse_diff_file_enhanced(diff, context_lines=5)
        assert len(result) == 1
        hunk = result[0].hunks[0]
        assert len(hunk.context_before) <= 5

    def test_context_after(self):
        diff = textwrap.dedent("""\
            --- a/mod.py
            +++ b/mod.py
            @@ -1,6 +1,7 @@
            +new_import
             line1
             line2
             line3
        """)
        result = parse_diff_file_enhanced(diff)
        hunk = result[0].hunks[0]
        assert len(hunk.context_after) > 0


# ── get_commit_messages ──────────────────────────────────────────────────

class TestGetCommitMessages:
    """Tests for commit message retrieval."""

    @patch("aicodereviewer.scanner.detect_vcs_type")
    @patch("subprocess.run")
    def test_git_returns_messages(self, mock_run, mock_vcs):
        mock_vcs.return_value = "git"
        mock_run.return_value = MagicMock(stdout="fix: resolved null pointer\n\nDetailed description")
        result = get_commit_messages("/repo", "HEAD~1..HEAD")
        assert result is not None
        assert "fix:" in result

    @patch("aicodereviewer.scanner.detect_vcs_type")
    @patch("subprocess.run")
    def test_svn_returns_messages(self, mock_run, mock_vcs):
        mock_vcs.return_value = "svn"
        mock_run.return_value = MagicMock(stdout="r42 | user | 2025-01-01\nfix bug")
        result = get_commit_messages("/repo", "41:42")
        assert result is not None

    @patch("aicodereviewer.scanner.detect_vcs_type")
    def test_no_vcs_returns_none(self, mock_vcs):
        mock_vcs.return_value = None
        assert get_commit_messages("/repo", "HEAD~1..HEAD") is None

    @patch("aicodereviewer.scanner.detect_vcs_type")
    @patch("subprocess.run")
    def test_failed_command_returns_none(self, mock_run, mock_vcs):
        import subprocess
        mock_vcs.return_value = "git"
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")
        assert get_commit_messages("/repo", "HEAD~1..HEAD") is None

    @patch("aicodereviewer.scanner.detect_vcs_type")
    @patch("subprocess.run")
    def test_empty_stdout_returns_none(self, mock_run, mock_vcs):
        mock_vcs.return_value = "git"
        mock_run.return_value = MagicMock(stdout="")
        assert get_commit_messages("/repo", "HEAD~1..HEAD") is None


# ── _build_diff_user_message ─────────────────────────────────────────────

class TestBuildDiffUserMessage:
    """Tests for the diff-aware prompt builder."""

    def _make_entry(self, *, with_hunks: bool = True, with_commit: bool = False):
        entry = {
            "filename": "src/app.py",
            "content": "line1\nline2",
            "is_diff": True,
        }
        if with_hunks:
            entry["hunks"] = [
                DiffHunk(
                    header="@@ -10,5 +10,6 @@ def authenticate_user():",
                    function_name="def authenticate_user():",
                    old_start=10,
                    new_start=10,
                    added=[(10, "    return user.first()"), (11, "    # Added .first()")],
                    removed=[(10, "    return user")],
                    context_before=["    user = db.query(User)", "    if user is None:", "        return None"],
                    context_after=["", "def other_func():"],
                ),
            ]
        if with_commit:
            entry["commit_messages"] = "fix: add .first() to prevent None return"
        return entry

    def test_includes_filename(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "src/app.py" in msg

    def test_includes_function_context(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "FUNCTION/CLASS CONTEXT" in msg
        assert "authenticate_user" in msg

    def test_includes_added_removed(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "+ L10:" in msg
        assert "- L10:" in msg

    def test_includes_surrounding_context(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "SURROUNDING CONTEXT (before change)" in msg
        assert "db.query" in msg

    def test_includes_focus_instruction(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "FOCUS YOUR REVIEW ON THE CHANGED LINES" in msg

    def test_includes_commit_messages(self):
        entry = self._make_entry(with_commit=True)
        msg = AIBackend._build_diff_user_message(entry, "security")
        assert "COMMIT MESSAGE" in msg
        assert ".first()" in msg

    def test_no_hunks_fallback(self):
        entry = self._make_entry(with_hunks=False)
        msg = AIBackend._build_diff_user_message(entry, "security")
        assert "CHANGED FILE: src/app.py" in msg
        # Should still include the content
        assert "line1" in msg

    def test_spec_preamble(self):
        entry = self._make_entry()
        msg = AIBackend._build_diff_user_message(entry, "specification", spec_content="requirement 1")
        assert "SPECIFICATION DOCUMENT" in msg
        assert "requirement 1" in msg

    def test_json_response_instruction(self):
        msg = AIBackend._build_diff_user_message(self._make_entry(), "security")
        assert "JSON" in msg


# ── _build_multi_file_diff_user_message ──────────────────────────────────

class TestBuildMultiFileDiffUserMessage:
    """Tests for the multi-file diff prompt builder."""

    def _make_entries(self):
        return [
            {
                "name": "file1.py",
                "content": "code1",
                "is_diff": True,
                "hunks": [DiffHunk(
                    header="@@ -1,2 +1,3 @@",
                    new_start=1,
                    old_start=1,
                    added=[(2, "new_line")],
                    removed=[],
                )],
                "commit_messages": "feat: add feature",
            },
            {
                "name": "file2.py",
                "content": "code2",
                "is_diff": True,
                "hunks": [DiffHunk(
                    header="@@ -5,2 +5,3 @@ class Foo:",
                    function_name="class Foo:",
                    new_start=5,
                    old_start=5,
                    added=[(6, "    pass")],
                    removed=[(5, "    old_line")],
                )],
            },
        ]

    def test_contains_both_files(self):
        msg = AIBackend._build_multi_file_diff_user_message(self._make_entries(), "security")
        assert "file1.py" in msg
        assert "file2.py" in msg

    def test_uses_file_delimiters(self):
        msg = AIBackend._build_multi_file_diff_user_message(self._make_entries(), "security")
        assert "=== FILE: file1.py ===" in msg
        assert "=== FILE: file2.py ===" in msg

    def test_includes_commit_message_once(self):
        msg = AIBackend._build_multi_file_diff_user_message(self._make_entries(), "security")
        assert msg.count("COMMIT MESSAGE") == 1

    def test_includes_diff_markers(self):
        msg = AIBackend._build_multi_file_diff_user_message(self._make_entries(), "security")
        assert "+ L2: new_line" in msg
        assert "- L5: " in msg

    def test_focus_instruction(self):
        msg = AIBackend._build_multi_file_diff_user_message(self._make_entries(), "security")
        assert "FOCUS YOUR REVIEW ON THE CHANGED LINES" in msg


# ── _is_diff_entry ───────────────────────────────────────────────────────

class TestIsDiffEntry:
    """Tests for diff-entry detection in reviewer."""

    def test_dict_with_is_diff_true(self):
        assert _is_diff_entry({"is_diff": True, "content": "x", "path": "a"})

    def test_dict_without_is_diff(self):
        assert not _is_diff_entry({"content": "x", "path": "a"})

    def test_path_object(self):
        assert not _is_diff_entry(Path("/some/file.py"))

    def test_dict_with_is_diff_false(self):
        assert not _is_diff_entry({"is_diff": False, "content": "x"})


# ── scan_project_with_scope enhanced output ──────────────────────────────

class TestScanProjectWithScopeEnhanced:
    """Verify that diff-scope now includes enhanced fields."""

    def test_diff_scope_has_is_diff(self, tmp_path):
        diff_file = tmp_path / "changes.patch"
        diff_file.write_text(textwrap.dedent("""\
            --- a/test.py
            +++ b/test.py
            @@ -1,2 +1,3 @@ def greet():
                 print("hello")
            +    print("world")
        """))
        result = __import__("aicodereviewer.scanner", fromlist=["scan_project_with_scope"]).scan_project_with_scope(
            str(tmp_path), scope="diff", diff_file=str(diff_file)
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["is_diff"] is True
        assert "hunks" in entry
        assert len(entry["hunks"]) == 1

    def test_diff_scope_hunk_has_function_name(self, tmp_path):
        diff_file = tmp_path / "changes.patch"
        diff_file.write_text(textwrap.dedent("""\
            --- a/test.py
            +++ b/test.py
            @@ -1,2 +1,3 @@ def greet():
                 print("hello")
            +    print("world")
        """))
        from aicodereviewer.scanner import scan_project_with_scope
        result = scan_project_with_scope(str(tmp_path), scope="diff", diff_file=str(diff_file))
        hunk = result[0]["hunks"][0]
        assert hunk.function_name is not None
        assert "greet" in hunk.function_name

    def test_diff_scope_backward_compat_fields(self, tmp_path):
        """Entry still has path, content, filename for backward compat."""
        diff_file = tmp_path / "changes.patch"
        diff_file.write_text(textwrap.dedent("""\
            --- a/test.py
            +++ b/test.py
            @@ -1,3 +1,4 @@
             line1
            +added
             line2
        """))
        from aicodereviewer.scanner import scan_project_with_scope
        result = scan_project_with_scope(str(tmp_path), scope="diff", diff_file=str(diff_file))
        entry = result[0]
        assert "path" in entry
        assert "content" in entry
        assert "filename" in entry
        assert "line1" in entry["content"]
