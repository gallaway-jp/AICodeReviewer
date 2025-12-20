# tests/test_backup.py
"""
Tests for AI Code Reviewer backup functionality
"""
import pytest
import tempfile
import time
import os
from pathlib import Path
from unittest.mock import patch
from aicodereviewer.backup import cleanup_old_backups


class TestCleanupOldBackups:
    """Test backup cleanup functionality"""

    def test_cleanup_old_backups_no_files(self):
        """Test cleanup when no backup files exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Should not raise any errors
            cleanup_old_backups(temp_dir)

    def test_cleanup_old_backups_recent_files(self):
        """Test cleanup with recent backup files (should not be deleted)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a recent backup file
            backup_file = Path(temp_dir) / "test.py.backup"
            backup_file.write_text("backup content")

            cleanup_old_backups(temp_dir)

            # File should still exist
            assert backup_file.exists()

    def test_cleanup_old_backups_old_files(self):
        """Test cleanup with old backup files (should be deleted)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create an old backup file
            backup_file = Path(temp_dir) / "old.py.backup"
            backup_file.write_text("old backup content")

            # Set modification time to 25 hours ago
            old_time = time.time() - (25 * 3600)
            os.utime(backup_file, (old_time, old_time))

            cleanup_old_backups(temp_dir)

            # File should be deleted
            assert not backup_file.exists()

    def test_cleanup_old_backups_mixed_files(self):
        """Test cleanup with mix of old and recent backup files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create recent backup file
            recent_backup = Path(temp_dir) / "recent.py.backup"
            recent_backup.write_text("recent content")

            # Create old backup file
            old_backup = Path(temp_dir) / "old.py.backup"
            old_backup.write_text("old content")
            old_time = time.time() - (25 * 3600)
            os.utime(old_backup, (old_time, old_time))

            cleanup_old_backups(temp_dir)

            # Recent file should exist, old file should not
            assert recent_backup.exists()
            assert not old_backup.exists()

    def test_cleanup_old_backups_nested_dirs(self):
        """Test cleanup with backup files in nested directories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory structure
            sub_dir = Path(temp_dir) / "src" / "utils"
            sub_dir.mkdir(parents=True)

            # Create old backup file in nested dir
            nested_backup = sub_dir / "nested.py.backup"
            nested_backup.write_text("nested backup")
            old_time = time.time() - (25 * 3600)
            os.utime(nested_backup, (old_time, old_time))

            cleanup_old_backups(temp_dir)

            # File should be deleted
            assert not nested_backup.exists()

    def test_cleanup_old_backups_custom_age(self):
        """Test cleanup with custom max age"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create backup file that's 2 hours old
            backup_file = Path(temp_dir) / "test.py.backup"
            backup_file.write_text("content")
            old_time = time.time() - (2 * 3600)  # 2 hours ago
            os.utime(backup_file, (old_time, old_time))

            # Clean up files older than 1 hour
            cleanup_old_backups(temp_dir, max_age_hours=1)

            # File should be deleted since it's 2 hours old
            assert not backup_file.exists()

    @patch('glob.glob')
    def test_cleanup_old_backups_glob_error(self, mock_glob):
        """Test handling glob errors gracefully"""
        mock_glob.side_effect = Exception("Glob error")

        # Should not raise exception
        cleanup_old_backups("/some/path")

    def test_cleanup_old_backups_delete_error(self):
        """Test handling file deletion errors gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create old backup file
            backup_file = Path(temp_dir) / "old.py.backup"
            backup_file.write_text("content")
            old_time = time.time() - (25 * 3600)
            os.utime(backup_file, (old_time, old_time))

            # Mock os.remove to raise an exception
            with patch('os.remove', side_effect=OSError("Delete failed")):
                # Should not raise exception
                cleanup_old_backups(temp_dir)