# tests/test_scanner.py
"""
Tests for AI Code Reviewer scanner functionality
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from aicodereviewer.scanner import scan_project, parse_diff_file, get_diff_from_commits, scan_project_with_scope


class TestScanProject:
    """Test project scanning functionality"""

    def test_scan_project_basic(self):
        """Test basic project scanning"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            py_file = Path(temp_dir) / "test.py"
            py_file.write_text("print('hello')")

            js_file = Path(temp_dir) / "test.js"
            js_file.write_text("console.log('hello')")

            txt_file = Path(temp_dir) / "readme.txt"
            txt_file.write_text("readme")

            result = scan_project(temp_dir)

            assert len(result) == 2  # Should find .py and .js files
            assert py_file in result
            assert js_file in result
            assert txt_file not in result

    def test_scan_project_ignore_dirs(self):
        """Test that ignored directories are skipped"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create ignored directories
            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "test.py").write_text("print('hello')")

            node_modules = Path(temp_dir) / "node_modules"
            node_modules.mkdir()
            (node_modules / "test.js").write_text("console.log('hello')")

            # Create valid file
            valid_file = Path(temp_dir) / "main.py"
            valid_file.write_text("print('valid')")

            result = scan_project(temp_dir)

            assert len(result) == 1
            assert valid_file in result

    def test_scan_project_nested_dirs(self):
        """Test scanning nested directories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested structure
            sub_dir = Path(temp_dir) / "src"
            sub_dir.mkdir()

            nested_file = sub_dir / "nested.py"
            nested_file.write_text("print('nested')")

            result = scan_project(temp_dir)

            assert len(result) == 1
            assert nested_file in result


class TestParseDiffFile:
    """Test diff file parsing functionality"""

    def test_parse_simple_diff(self):
        """Test parsing a simple unified diff"""
        diff_content = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 print("hello")
+print("world")
"""
        result = parse_diff_file(diff_content)

        assert len(result) == 1
        assert result[0]['filename'] == 'test.py'
        assert 'print("hello")' in result[0]['content']
        assert 'print("world")' in result[0]['content']

    def test_parse_multiple_files(self):
        """Test parsing diff with multiple files"""
        diff_content = """--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
 print("file1")
+print("added")
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
 print("file2")
+print("modified")
"""
        result = parse_diff_file(diff_content)

        assert len(result) == 2
        filenames = [f['filename'] for f in result]
        assert 'file1.py' in filenames
        assert 'file2.py' in filenames

    def test_parse_empty_diff(self):
        """Test parsing empty diff"""
        result = parse_diff_file("")
        assert result == []

    def test_parse_diff_without_changes(self):
        """Test parsing diff header without actual changes"""
        diff_content = """--- a/test.py
+++ b/test.py
"""
        result = parse_diff_file(diff_content)
        assert result == []


class TestGetDiffFromCommits:
    """Test git diff generation functionality"""

    @patch('subprocess.run')
    def test_get_diff_from_commits_success(self, mock_run):
        """Test successful git diff generation"""
        mock_process = MagicMock()
        mock_process.stdout = "diff content here"
        mock_run.return_value = mock_process

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result == "diff content here"
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_get_diff_from_commits_error(self, mock_run):
        """Test git diff generation with error"""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'git', "Git error")

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result is None

    @patch('subprocess.run')
    def test_get_diff_from_commits_git_not_found(self, mock_run):
        """Test git diff when git is not installed"""
        mock_run.side_effect = FileNotFoundError()

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result is None


class TestScanProjectWithScope:
    """Test project scanning with different scopes"""

    def test_scan_project_scope(self):
        """Test scanning with project scope"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("print('hello')")

            result = scan_project_with_scope(temp_dir, scope='project')

            assert len(result) == 1
            assert result[0] == test_file

    def test_scan_diff_scope_with_file(self):
        """Test scanning with diff scope using diff file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create diff file
            diff_content = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 print("hello")
+print("world")
"""
            diff_file = Path(temp_dir) / "changes.patch"
            diff_file.write_text(diff_content)

            # Create the actual file
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text('print("hello")\nprint("world")')

            result = scan_project_with_scope(
                temp_dir,
                scope='diff',
                diff_file=str(diff_file)
            )

            assert len(result) == 1
            assert result[0]['filename'] == 'test.py'
            assert 'print("hello")' in result[0]['content']
            assert 'print("world")' in result[0]['content']

    def test_scan_diff_scope_file_not_found(self):
        """Test scanning with diff scope when file doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = scan_project_with_scope(
                temp_dir,
                scope='diff',
                diff_file='nonexistent.patch'
            )

            assert result == []

    @patch('aicodereviewer.scanner.get_diff_from_commits')
    def test_scan_diff_scope_with_commits(self, mock_get_diff):
        """Test scanning with diff scope using commits"""
        mock_get_diff.return_value = """--- a/test.py
+++ b/test.py
@@ -1,1 +1,2 @@
 print("hello")
+print("world")
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create the actual file
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text('print("hello")\nprint("world")')

            result = scan_project_with_scope(
                temp_dir,
                scope='diff',
                commits='HEAD~1..HEAD'
            )

            assert len(result) == 1
            assert result[0]['filename'] == 'test.py'

    def test_scan_diff_scope_no_diff_content(self):
        """Test scanning with diff scope when no diff content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = scan_project_with_scope(
                temp_dir,
                scope='diff'
            )

            assert result == []