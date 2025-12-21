"""
Tests for AI Code Reviewer diff functionality
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the functions we want to test
from aicodereviewer.scanner import parse_diff_file, get_diff_from_commits, scan_project_with_scope


class TestDiffParsing:
    """Test diff file parsing functionality"""

    def test_parse_simple_diff(self):
        """Test parsing a simple unified diff"""
        diff_content = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
     print("Hello")
+    print("World")
"""

        result = parse_diff_file(diff_content)

        assert len(result) == 1
        assert result[0]['filename'] == 'test.py'
        assert 'def hello():' in result[0]['content']
        assert 'print("Hello")' in result[0]['content']
        assert 'print("World")' in result[0]['content']

    def test_parse_multiple_files(self):
        """Test parsing diff with multiple files"""
        diff_content = """--- a/file1.py
+++ b/file1.py
@@ -1,2 +1,3 @@
 def func1():
     pass
+    print("added")

--- a/file2.py
+++ b/file2.py
@@ -1,2 +1,3 @@
 def func2():
     pass
+    return True
"""

        result = parse_diff_file(diff_content)

        assert len(result) == 2

        # Check first file
        assert result[0]['filename'] == 'file1.py'
        assert 'def func1():' in result[0]['content']
        assert 'print("added")' in result[0]['content']

        # Check second file
        assert result[1]['filename'] == 'file2.py'
        assert 'def func2():' in result[1]['content']
        assert 'return True' in result[1]['content']

    def test_parse_diff_with_context_lines(self):
        """Test parsing diff with context lines"""
        diff_content = """--- a/example.py
+++ b/example.py
@@ -1,5 +1,6 @@
 def calculate(x, y):
     result = x + y
     print(f"Result: {result}")
+    log_result(result)
     return result

 def log_result(value):
"""

        result = parse_diff_file(diff_content)

        assert len(result) == 1
        content = result[0]['content']
        assert 'def calculate(x, y):' in content
        assert 'result = x + y' in content
        assert 'log_result(result)' in content
        assert 'def log_result(value):' in content

    def test_parse_empty_diff(self):
        """Test parsing empty diff content"""
        result = parse_diff_file("")
        assert result == []

    def test_parse_diff_without_changes(self):
        """Test parsing diff with only file headers"""
        diff_content = """--- a/test.py
+++ b/test.py
"""
        result = parse_diff_file(diff_content)
        assert result == []


class TestGitDiffGeneration:
    """Test git diff generation functionality"""

    @patch('aicodereviewer.scanner.detect_vcs_type')
    @patch('subprocess.run')
    def test_get_diff_from_commits_success(self, mock_run, mock_detect_vcs):
        """Test successful git diff generation"""
        mock_detect_vcs.return_value = 'git'
        mock_result = MagicMock()
        mock_result.stdout = "diff content here"
        mock_run.return_value = mock_result

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result == "diff content here"
        mock_run.assert_called_once_with(
            ['git', 'diff', 'HEAD~1..HEAD'],
            cwd='/path/to/project',
            capture_output=True,
            text=True,
            check=True
        )

    @patch('aicodereviewer.scanner.detect_vcs_type')
    @patch('subprocess.run')
    def test_get_diff_from_commits_error(self, mock_run, mock_detect_vcs):
        """Test git diff generation with error"""
        mock_detect_vcs.return_value = 'git'
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'git', "Git error")

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result is None

    @patch('aicodereviewer.scanner.detect_vcs_type')
    @patch('subprocess.run')
    def test_get_diff_from_commits_git_not_found(self, mock_run, mock_detect_vcs):
        """Test git diff when git is not installed"""
        mock_detect_vcs.return_value = 'git'
        mock_run.side_effect = FileNotFoundError()

        result = get_diff_from_commits("/path/to/project", "HEAD~1..HEAD")

        assert result is None


class TestProjectScanning:
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
@@ -1,2 +1,3 @@
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
            result = scan_project_with_scope(temp_dir, scope='diff')

            assert result == []


class TestIntegration:
    """Integration tests for the diff functionality"""

    def test_complete_workflow(self):
        """Test a complete diff parsing and file scanning workflow"""
        diff_content = """--- a/src/main.py
+++ b/src/main.py
@@ -1,4 +1,5 @@
 def main():
     print("Hello")
+    print("AI Code Review")
     return True

--- a/src/utils.py
+++ b/src/utils.py
@@ -1,2 +1,4 @@
 def helper():
     pass
+
+def new_feature():
+    return "added"
"""

        # Test diff parsing
        parsed_files = parse_diff_file(diff_content)
        assert len(parsed_files) == 2

        # Verify file 1
        assert parsed_files[0]['filename'] == 'src/main.py'
        assert 'def main():' in parsed_files[0]['content']
        assert 'print("AI Code Review")' in parsed_files[0]['content']

        # Verify file 2
        assert parsed_files[1]['filename'] == 'src/utils.py'
        assert 'def helper():' in parsed_files[1]['content']
        assert 'def new_feature():' in parsed_files[1]['content']


if __name__ == "__main__":
    pytest.main([__file__])