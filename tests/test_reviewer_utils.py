"""
Tests for reviewer utilities such as file caching and size handling.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from aicodereviewer import reviewer


def test_read_file_content_caches_small_files():
    reviewer._file_content_cache.clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "sample.py"
        file_path.write_text("print('hello')\n")

        first_read = reviewer._read_file_content(file_path)
        assert first_read.startswith("print('hello')")

        # While the file still exists on disk, a second read should use the cache.
        second_read = reviewer._read_file_content(file_path)
        assert second_read == first_read
        assert str(file_path) in reviewer._file_content_cache

        # After deleting the file, the mtime-aware cache correctly
        # invalidates the stale entry and returns None → empty re-read.
        os.remove(file_path)
        third_read = reviewer._read_file_content(file_path)
        assert third_read == ""  # file no longer on disk


def test_read_file_content_skips_large_files():
    reviewer._file_content_cache.clear()

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "big.py"
        file_path.write_text("x = 1\n")

        with patch('aicodereviewer.reviewer.os.path.getsize', return_value=reviewer.config.get('performance', 'max_file_size_mb') + 1):
            content = reviewer._read_file_content(file_path)

        assert content == ""
        assert len(reviewer._file_content_cache) == 0


def test_parse_severity_keywords():
    assert reviewer._parse_severity("This is a CRITICAL vulnerability") == "critical"
    assert reviewer._parse_severity("High risk security issue") == "high"
    assert reviewer._parse_severity("Minor, low impact bug") == "low"
    assert reviewer._parse_severity("Informational note only") == "info"
    # Default stays medium
    assert reviewer._parse_severity("General feedback without severity") == "medium"
