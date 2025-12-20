# src/aicodereviewer/backup.py
"""
Backup file management and cleanup utilities.

This module handles automatic cleanup of backup files created during
AI fix operations to prevent disk space accumulation over time.

Functions:
    cleanup_old_backups: Remove backup files older than specified age
"""
import glob
import os
import time


def cleanup_old_backups(project_path: str, max_age_hours: int = 24):
    """
    Clean up old backup files to manage disk space usage.

    Automatically removes .backup files that are older than the specified
    maximum age. This prevents accumulation of backup files from AI fix
    operations while preserving recent backups for safety.

    Args:
        project_path (str): Root directory to search for backup files
        max_age_hours (int): Maximum age in hours for backup files (default: 24)

    Note:
        Uses glob pattern matching to find all .backup files recursively.
        Silently ignores deletion errors to avoid interrupting main workflow.
    """
    try:
        backup_pattern = os.path.join(project_path, "**", "*.backup")
        backup_files = glob.glob(backup_pattern, recursive=True)

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        for backup_file in backup_files:
            if os.path.getmtime(backup_file) < current_time - max_age_seconds:
                try:
                    os.remove(backup_file)
                    print(f"🗑️ Cleaned up old backup: {backup_file}")
                except OSError:
                    pass  # Ignore if can't delete
    except Exception:
        pass  # Don't fail if cleanup doesn't work