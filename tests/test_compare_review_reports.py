from __future__ import annotations

import json
from pathlib import Path

from tools.compare_review_reports import compare_reports


def test_compare_reports_detects_added_and_removed_issues(tmp_path: Path) -> None:
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"

    before_path.write_text(
        json.dumps(
            {
                "report": {
                    "issues_found": [
                        {
                            "file_path": "src/admin.py",
                            "line_number": 5,
                            "issue_type": "authorization",
                            "severity": "high",
                            "context_scope": "cross_file",
                            "related_files": ["src/auth.py"],
                            "description": "Missing admin guard",
                        },
                        {
                            "file_path": "src/auth.py",
                            "line_number": 1,
                            "issue_type": "input_validation",
                            "severity": "medium",
                            "context_scope": "local",
                            "related_files": [],
                            "description": "Weak id validation",
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(
            {
                "report": {
                    "issues_found": [
                        {
                            "file_path": "src/admin.py",
                            "line_number": 5,
                            "issue_type": "authorization",
                            "severity": "critical",
                            "context_scope": "cross_file",
                            "related_files": ["src/auth.py"],
                            "description": "Missing admin guard",
                        },
                        {
                            "file_path": "src/auth.py",
                            "line_number": 1,
                            "issue_type": "authorization",
                            "severity": "medium",
                            "context_scope": "cross_file",
                            "related_files": ["src/admin.py"],
                            "description": "Unused admin guard",
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = compare_reports(before_path, after_path)

    assert result["before"]["issue_count"] == 2
    assert result["after"]["issue_count"] == 2
    assert result["delta"]["unchanged_count"] == 1
    assert result["delta"]["added_count"] == 1
    assert result["delta"]["removed_count"] == 1
    assert result["delta"]["added"][0]["file"] == "auth.py"
    assert result["delta"]["removed"][0]["issue_type"] == "input_validation"