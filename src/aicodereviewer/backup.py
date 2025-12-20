# src/aicodereviewer/backup.py
import glob
import os
import time


def cleanup_old_backups(project_path: str, max_age_hours: int = 24):
    """Clean up old backup files to prevent disk space issues"""
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