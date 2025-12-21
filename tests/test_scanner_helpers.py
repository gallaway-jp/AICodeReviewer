"""
Tests for scanner helper utilities such as VCS root detection and range normalization.
"""
import tempfile
from pathlib import Path

from aicodereviewer.scanner import _find_vcs_root, _normalize_commit_range, detect_vcs_type


def test_normalize_commit_range_svn_and_git():
    assert _normalize_commit_range('git', 'HEAD~1..HEAD') == 'HEAD~1..HEAD'
    assert _normalize_commit_range('svn', '100..101') == '100:101'
    assert _normalize_commit_range('svn', '200:201') == '200:201'


def test_find_vcs_root_and_detect_vcs_type():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / '.git').mkdir()
        nested = root / 'src' / 'pkg'
        nested.mkdir(parents=True)

        # Should walk up to find the .git directory
        assert _find_vcs_root(str(nested), 'git') == root

        # detect_vcs_type should also identify git when called from a subdirectory
        assert detect_vcs_type(str(nested)) == 'git'
