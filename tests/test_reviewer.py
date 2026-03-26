# tests/test_reviewer.py
"""
Tests for AI Code Reviewer reviewer functionality.

Updated for v2.0 API: collect_review_issues now takes review_types (List[str])
instead of a single review_type string.
"""
import json
from unittest.mock import MagicMock, patch
from pathlib import Path
from typing import List
from aicodereviewer.reviewer import collect_review_issues, verify_issue_resolved, FileInfo, _merge_combined_with_fallback
from aicodereviewer.models import ReviewIssue


class TestCollectReviewIssues:
    """Test review issue collection functionality"""

    def test_collect_review_issues_project_scope(self):
        """Test collecting issues from project scope files"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has security issues"

        mock_file = Path("/path/to/test.py")
        target_files: List[FileInfo] = [mock_file]  # type: ignore[list-item]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test code')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(mock_file)
        assert issues[0].issue_type == "security"
        assert issues[0].severity == "medium"
        assert "security issues" in issues[0].ai_feedback

    def test_collect_review_issues_diff_scope(self):
        """Test collecting issues from diff scope files"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "This code has performance issues"

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
            'path': Path("/path/to/test.py"),
            'content': "print('modified code')",
            'filename': 'test.py'
        }]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].file_path == str(Path("/path/to/test.py"))
        assert issues[0].issue_type == "performance"
        assert "performance issues" in issues[0].ai_feedback

    def test_collect_review_issues_multiple_types(self):
        """Test collecting issues across multiple review types (combined prompt)."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Security vulnerability found"

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
            'path': Path("/path/to/test.py"),
            'content': "print('code')",
            'filename': 'test.py'
        }]

        issues = collect_review_issues(
            target_files, ["security", "performance"], mock_client, "en"
        )

        # Combined into a single prompt, so one call and one issue
        assert len(issues) == 1
        assert issues[0].issue_type == "security+performance"
        mock_client.get_review.assert_called_once()

    def test_collect_review_issues_no_feedback(self):
        """Test collecting issues when AI returns error"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Error: Something went wrong"

        target_files: List[FileInfo] = [Path("/path/to/test.py")]  # type: ignore[list-item]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_retries_single_file_transient_error(self):
        """Single-file reviews retry once on transient backend errors."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Request timed out",
            "Recovered feedback after retry",
        ]

        target_files: List[FileInfo] = [Path("/path/to/test.py")]  # type: ignore[list-item]

        with patch('builtins.open', MagicMock()) as mock_open, \
             patch('os.path.getsize', return_value=1000):
            mock_open.return_value.__enter__.return_value.read.return_value = "print('test')"
            issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 1
        assert mock_client.get_review.call_count == 2

    def test_collect_review_issues_retries_combined_batch_transient_error(self):
        """Combined multi-file reviews retry once before falling back."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            json.dumps({
                "files": [
                    {
                        "filename": "a.py",
                        "findings": [{
                            "severity": "high",
                            "category": "security",
                            "title": "Issue A",
                            "description": "Combined retry recovered first file",
                        }],
                    },
                    {
                        "filename": "b.py",
                        "findings": [{
                            "severity": "medium",
                            "category": "security",
                            "title": "Issue B",
                            "description": "Combined retry recovered second file",
                        }],
                    },
                ],
            }),
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path("/path/to/a.py"),
                'content': "print('a')",
                'filename': 'a.py'
            },
            {
                'path': Path("/path/to/b.py"),
                'content': "print('b')",
                'filename': 'b.py'
            },
        ]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 2
        assert {Path(issue.file_path).name for issue in issues} == {"a.py", "b.py"}
        assert mock_client.get_review.call_count >= 2

    @patch("aicodereviewer.reviewer._process_files_individually")
    @patch("aicodereviewer.reviewer.parse_review_response")
    def test_collect_review_issues_retries_small_empty_combined_batch_individually(
        self,
        mock_parse_review_response,
        mock_process_files_individually,
    ):
        """A small combined batch that parses to zero issues should retry per-file before accepting a clean result."""
        mock_parse_review_response.return_value = []
        mock_process_files_individually.return_value = [
            ReviewIssue(file_path="/path/to/a.py", issue_type="security", severity="medium", description="A"),
            ReviewIssue(file_path="/path/to/b.py", issue_type="security", severity="medium", description="B"),
        ]

        file_entries = [
            {"path": "/path/to/a.py", "name": "a.py", "content": "print('a')"},
            {"path": "/path/to/b.py", "name": "b.py", "content": "print('b')"},
        ]
        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {"path": Path("/path/to/a.py"), "content": "print('a')", "filename": "a.py"},
            {"path": Path("/path/to/b.py"), "content": "print('b')", "filename": "b.py"},
        ]

        issues = _merge_combined_with_fallback(
            "{}",
            file_entries,
            "security",
            target_files,
            MagicMock(),
            "en",
            None,
            None,
        )

        assert len(issues) == 2
        assert {Path(issue.file_path).name for issue in issues} == {"a.py", "b.py"}
        mock_process_files_individually.assert_called_once()

    def test_collect_review_issues_adds_deterministic_cache_finding_when_model_misses_it(self):
        """Performance reviews add a narrow stale-cache supplement for obvious cross-file read/write splits."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/cache.py'),
                'content': (
                    'PROFILE_CACHE = {}\n\n'
                    'def get_user_profile(user_id):\n'
                    '    return PROFILE_CACHE.get(user_id)\n\n'
                    'def set_user_profile(user_id, profile):\n'
                    '    PROFILE_CACHE[user_id] = profile\n'
                ),
                'filename': 'cache.py'
            },
            {
                'path': Path('/path/to/profile_service.py'),
                'content': (
                    'def update_user_profile(store, user_id, profile):\n'
                    '    store[user_id] = profile\n'
                ),
                'filename': 'profile_service.py'
            },
        ]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "missing_cache_invalidation"
        assert issue.context_scope == "cross_file"
        assert Path(issue.file_path).name == "profile_service.py"
        assert [Path(path).name for path in issue.related_files] == ["cache.py"]
        assert "user_profile" in (issue.evidence_basis or "")

    def test_collect_review_issues_promotes_local_cache_issue_from_related_cross_file_issue(self):
        """Local cache issues are promoted when sibling issues prove a cross-file stale-state dependency."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "cache.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "missing_cache_invalidation",
                            "title": "Missing cache invalidation",
                            "description": "Cache entries are never invalidated.",
                            "context_scope": "local",
                            "evidence_basis": "set_user_profile updates cache but no corresponding invalidate or clear mechanism exists",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "profile_service.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "high",
                            "category": "contract_mismatch",
                            "title": "Mismatched write path",
                            "description": "The service writes via store while cache.py serves cached values.",
                            "context_scope": "cross_file",
                            "related_files": ["cache.py"],
                            "systemic_impact": "Stale cache state can reach callers.",
                            "evidence_basis": "profile_service.py updates a different store than cache.py reads.",
                        }
                    ],
                },
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/cache.py'),
                'content': 'def set_user_profile(user_id, profile):\n    PROFILE_CACHE[user_id] = profile\n',
                'filename': 'cache.py'
            },
            {
                'path': Path('/path/to/profile_service.py'),
                'content': 'def update_user_profile(store, user_id, profile):\n    store[user_id] = profile\n',
                'filename': 'profile_service.py'
            },
        ]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        cache_issue = next(issue for issue in issues if issue.issue_type == "missing_cache_invalidation")
        assert cache_issue.context_scope == "cross_file"
        assert [Path(path).name for path in cache_issue.related_files] == ["profile_service.py", "cache.py"]
        assert cache_issue.systemic_impact is not None
        assert "stale" in cache_issue.systemic_impact.lower()

    def test_collect_review_issues_normalizes_api_design_subtype_category(self):
        """API design reviews should collapse known subtype labels back to the canonical api_design type."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "api.py",
                    "findings": [
                        {
                            "issue_id": "issue-api-0001",
                            "severity": "high",
                            "category": "HTTP method / endpoint semantics",
                            "title": "Create exposed as GET",
                            "description": "The endpoint uses GET even though it creates data.",
                            "evidence_basis": "@app.get is used on a create handler.",
                        }
                    ],
                }
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': '@app.get("/api/invitations/create")\ndef create_invitation(payload):\n    INVITATIONS.append(payload)\n',
                'filename': 'api.py'
            }
        ]

        issues = collect_review_issues(target_files, ["api_design"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].issue_type == "api_design"

    def test_collect_review_issues_adds_get_create_api_design_finding_when_model_misses_it(self):
        """API design reviews add a deterministic finding for obvious GET create routes when the model misses the route semantics."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "api.py",
                    "findings": [
                        {
                            "issue_id": "issue-api-0002",
                            "severity": "low",
                            "category": "Security",
                            "title": "Missing auth",
                            "description": "The endpoint is unauthenticated.",
                            "evidence_basis": "No authentication guard exists.",
                        }
                    ],
                }
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from fastapi import FastAPI\n\n'
                    'app = FastAPI()\n'
                    'INVITATIONS = []\n\n'
                    '@app.get("/api/invitations/create")\n'
                    'def create_invitation(payload):\n'
                    '    invitation = {"email": payload["email"]}\n'
                    '    INVITATIONS.append(invitation)\n'
                    '    return invitation\n'
                ),
                'filename': 'api.py'
            }
        ]

        issues = collect_review_issues(target_files, ["api_design"], mock_client, "en")

        api_issue = next(issue for issue in issues if issue.issue_type == "api_design")
        assert api_issue.severity == "high"
        assert "@app.get('/api/invitations/create')" in (api_issue.ai_feedback or "")
        assert "mutates server state" in (api_issue.evidence_basis or "")

    def test_collect_review_issues_adds_platform_open_compatibility_finding_when_model_misses_it(self):
        """Compatibility reviews add a deterministic finding for macOS-only open-command launchers when the model misses the OS breakage."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "report_viewer.py",
                    "findings": [
                        {
                            "issue_id": "issue-comp-0001",
                            "severity": "low",
                            "category": "Compatibility",
                            "title": "check=True issue",
                            "description": "check=True may be unsupported.",
                            "evidence_basis": "subprocess.run uses check=True.",
                        }
                    ],
                }
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/report_viewer.py'),
                'content': (
                    'import subprocess\n\n'
                    'def open_exported_report(report_path):\n'
                    '    subprocess.run(["open", report_path], check=True)\n'
                ),
                'filename': 'report_viewer.py'
            }
        ]

        issues = collect_review_issues(target_files, ["compatibility"], mock_client, "en")

        compatibility_issue = next(
            issue for issue in issues
            if issue.issue_type == "compatibility" and issue.severity == "medium"
        )
        assert "macOS-only 'open' command" in (compatibility_issue.evidence_basis or "")
        assert "Windows or Linux" in (compatibility_issue.systemic_impact or "")

    def test_collect_review_issues_normalizes_concurrency_parallelism_label(self):
        """Concurrency reviews should collapse generic concurrency subtype labels back to the canonical concurrency type."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "reservations.py",
                    "findings": [
                        {
                            "issue_id": "issue-con-0001",
                            "severity": "high",
                            "category": "Concurrency and Parallelism",
                            "title": "Slot race",
                            "description": "Coroutines race on shared slot state.",
                            "evidence_basis": "available_slots is updated without synchronization.",
                        }
                    ],
                }
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/reservations.py'),
                'content': (
                    'class SlotAllocator:\n'
                    '    async def reserve_slot(self, request):\n'
                    '        remaining = self.available_slots.get(request["slot_id"], 0)\n'
                    '        await self._load_policy(request["user_id"])\n'
                    '        self.available_slots[request["slot_id"]] = remaining - 1\n'
                ),
                'filename': 'reservations.py'
            }
        ]

        issues = collect_review_issues(target_files, ["concurrency"], mock_client, "en")

        assert len(issues) == 1
        assert issues[0].issue_type == "concurrency"

    def test_collect_review_issues_adds_n_plus_one_performance_finding_when_model_misses_it(self):
        """Performance reviews add a narrow supplement for obvious cross-file query-in-loop patterns."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/order_service.py'),
                'content': (
                    'from src.order_repository import fetch_order\n\n'
                    'def build_dashboard_order_summaries(order_ids):\n'
                    '    summaries = []\n'
                    '    for order_id in order_ids:\n'
                    '        summaries.append(fetch_order(order_id))\n'
                    '    return summaries\n'
                ),
                'filename': 'order_service.py'
            },
            {
                'path': Path('/path/to/order_repository.py'),
                'content': (
                    'def fetch_order(order_id):\n'
                    '    return execute_query("SELECT * FROM orders WHERE id = ?", [order_id])[0]\n\n'
                    'def fetch_orders(order_ids):\n'
                    '    return execute_query("SELECT * FROM orders WHERE id IN (?)", order_ids)\n'
                ),
                'filename': 'order_repository.py'
            },
        ]

        issues = collect_review_issues(target_files, ["performance"], mock_client, "en")

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "performance"
        assert issue.context_scope == "cross_file"
        assert Path(issue.file_path).name == "order_service.py"
        assert [Path(path).name for path in issue.related_files] == ["order_repository.py"]
        assert "fetch_order" in (issue.evidence_basis or "")
        assert "Latency" in (issue.ai_feedback or "")

    def test_collect_review_issues_enriches_controller_repository_bypass_evidence(self):
        """Architecture reviews should enrich controller bypass findings so the evidence names the missing service boundary."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "orders_controller.py",
                    "findings": [
                        {
                            "issue_id": "issue-arch-0001",
                            "severity": "high",
                            "category": "architecture",
                            "title": "Controller bypasses repository",
                            "description": "The controller imports the repository directly instead of staying thin.",
                            "context_scope": "project",
                            "related_files": ["src/repositories/order_repository.py"],
                            "systemic_impact": "The controller becomes tightly coupled to persistence code.",
                            "evidence_basis": "orders_controller.py imports fetch_recent_orders from the repository directly.",
                        }
                    ],
                }
            ]
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/src/web/orders_controller.py'),
                'content': (
                    'from src.repositories.order_repository import fetch_recent_orders\n\n'
                    'def orders_page():\n'
                    '    return {"orders": fetch_recent_orders()}\n'
                ),
                'filename': 'orders_controller.py'
            },
            {
                'path': Path('/path/to/src/services/order_service.py'),
                'content': (
                    'from src.db import execute_query\n\n'
                    'def list_orders():\n'
                    '    return execute_query("SELECT id FROM orders")\n'
                ),
                'filename': 'order_service.py'
            },
            {
                'path': Path('/path/to/src/repositories/order_repository.py'),
                'content': (
                    'from src.db import execute_query\n\n'
                    'def fetch_recent_orders():\n'
                    '    return execute_query("SELECT id FROM orders")\n'
                ),
                'filename': 'order_repository.py'
            },
        ]

        issues = collect_review_issues(target_files, ["architecture"], mock_client, "en")

        assert len(issues) >= 1
        controller_issue = next(issue for issue in issues if Path(issue.file_path).name == "orders_controller.py")
        assert controller_issue.issue_type == "architecture"
        assert "service" in (controller_issue.evidence_basis or "").lower()
        assert "order_service.py" in ",".join(Path(path).name for path in controller_issue.related_files)

    def test_collect_review_issues_adds_controller_repository_bypass_finding_when_model_misses_it(self):
        """Architecture reviews add a narrow supplement when a controller imports a repository directly despite an available service layer."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/src/web/orders_controller.py'),
                'content': (
                    'from src.repositories.order_repository import fetch_recent_orders\n\n'
                    'def orders_page():\n'
                    '    return {"orders": fetch_recent_orders()}\n'
                ),
                'filename': 'orders_controller.py'
            },
            {
                'path': Path('/path/to/src/services/order_service.py'),
                'content': (
                    'from src.db import execute_query\n\n'
                    'def list_orders():\n'
                    '    return execute_query("SELECT id FROM orders")\n'
                ),
                'filename': 'order_service.py'
            },
            {
                'path': Path('/path/to/src/repositories/order_repository.py'),
                'content': (
                    'from src.db import execute_query\n\n'
                    'def fetch_recent_orders():\n'
                    '    return execute_query("SELECT id FROM orders")\n'
                ),
                'filename': 'order_repository.py'
            },
        ]

        issues = collect_review_issues(target_files, ["architecture"], mock_client, "en")

        controller_issue = next(issue for issue in issues if Path(issue.file_path).name == "orders_controller.py")
        assert controller_issue.issue_type == "architecture"
        assert controller_issue.context_scope == "project"
        assert "layer" in (controller_issue.systemic_impact or "").lower()
        assert "service" in (controller_issue.evidence_basis or "").lower()

    def test_collect_review_issues_adds_return_shape_mismatch_finding_when_model_misses_it(self):
        """Best-practices reviews add a narrow cross-file supplement for stale caller field expectations."""
        mock_client = MagicMock()
        mock_client.get_review.side_effect = [
            "Error: Temporary backend failure",
            "Error: Temporary backend failure",
            "",
            "",
        ]

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/service.py'),
                'content': (
                    'def build_result(total: int) -> dict:\n'
                    '    return {\n'
                    '        "value": total,\n'
                    '        "status": "ok",\n'
                    '    }\n'
                ),
                'filename': 'service.py'
            },
            {
                'path': Path('/path/to/client.py'),
                'content': (
                    'from src.service import build_result\n\n'
                    'def render_total(total: int) -> str:\n'
                    '    response = build_result(total)\n'
                    '    return f"Total: {response[\'result\']}"\n'
                ),
                'filename': 'client.py'
            },
        ]

        issues = collect_review_issues(target_files, ["best_practices"], mock_client, "en")

        assert len(issues) == 1
        issue = issues[0]
        assert issue.issue_type == "api_mismatch_runtime_error"
        assert issue.context_scope == "cross_file"
        assert issue.line_number == 5
        assert Path(issue.file_path).name == "client.py"
        assert [Path(path).name for path in issue.related_files] == ["service.py"]
        assert "result" in (issue.evidence_basis or "")
        assert "value" in (issue.evidence_basis or "")

    def test_collect_review_issues_adds_local_cross_tab_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "settings_window.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Missing Save Confirmation",
                            "description": "The save button does not provide confirmation.",
                            "context_scope": "local",
                            "evidence_basis": "save_settings does not report a saved state.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "sync_tab.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "low",
                            "category": "ui_ux",
                            "title": "Unclear Sync Tab Functionality",
                            "description": "The tab does not explain its controls well.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/settings_window.py'),
                'content': (
                    'from .sync_tab import SyncTab\n\n'
                    'class SettingsWindow:\n'
                    '    def save_settings(self):\n'
                    '        payload = self.sync_tab.collect_settings()\n'
                    '        if self.performance_mode.get() == "lite":\n'
                    '            payload["sync_enabled"] = False\n'
                    '        return payload\n'
                ),
                'filename': 'settings_window.py'
            },
            {
                'path': Path('/path/to/sync_tab.py'),
                'content': (
                    'class SyncTab:\n'
                    '    def collect_settings(self):\n'
                    '        return {"sync_enabled": True, "sync_on_startup": True}\n'
                ),
                'filename': 'sync_tab.py'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "sync_enabled" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "settings_window.py"
        assert [Path(path).name for path in supplement.related_files] == ["sync_tab.py"]
        assert "silently" in (supplement.systemic_impact or "")
        assert "sync_enabled" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_confirmation_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "settings_dialog.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "ui_ux",
                            "title": "Missing Confirmation for Destructive Action",
                            "description": "The reset button does not prompt the user before clearing settings.",
                            "context_scope": "local",
                            "evidence_basis": "The button is wired directly to self.reset_everything.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "settings_store.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "info",
                            "category": "ui_ux",
                            "title": "Global settings mutate immediately",
                            "description": "The store reset changes global settings right away.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/settings_dialog.py'),
                'content': (
                    'from .settings_store import reset_all_settings\n\n'
                    'class SettingsDialog:\n'
                    '    def reset_everything(self) -> None:\n'
                    '        reset_all_settings()\n'
                    '        self.status_var.set("All settings were reset.")\n'
                    '        self.destroy()\n'
                ),
                'filename': 'settings_dialog.py'
            },
            {
                'path': Path('/path/to/settings_store.py'),
                'content': (
                    'def reset_all_settings() -> None:\n'
                    '    global SETTINGS\n'
                    '    SETTINGS = {"theme": "system"}\n'
                ),
                'filename': 'settings_store.py'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "reset_all_settings" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "settings_dialog.py"
        assert [Path(path).name for path in supplement.related_files] == ["settings_store.py"]
        assert "accidental" in (supplement.systemic_impact or "")
        assert "reset_all_settings" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_wizard_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "advanced_step.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "info",
                            "category": "ui_ux",
                            "title": "Missing Loading/Error/Empty States",
                            "description": "The dialog lacks more feedback states.",
                            "context_scope": "local",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "setup_wizard.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Wizard Step Orientation Issue",
                            "description": "The wizard does not show enough progress.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/setup_wizard.py'),
                'content': (
                    'from .advanced_step import AdvancedStep\n\n'
                    'class SetupWizard:\n'
                    '    def __init__(self):\n'
                    '        self.cloud_sync_enabled = tk.BooleanVar(value=False)\n'
                    '        tk.Checkbutton(self, text="Enable cloud sync", variable=self.cloud_sync_enabled)\n\n'
                    '    def open_advanced_step(self):\n'
                    '        AdvancedStep(self, cloud_sync_enabled=self.cloud_sync_enabled.get())\n'
                ),
                'filename': 'setup_wizard.py'
            },
            {
                'path': Path('/path/to/advanced_step.py'),
                'content': (
                    'class AdvancedStep:\n'
                    '    def __init__(self, master=None, *, cloud_sync_enabled=False):\n'
                    '        tk.Checkbutton(self, text="Sync in background", state="normal" if cloud_sync_enabled else "disabled")\n'
                ),
                'filename': 'advanced_step.py'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "Enable cloud sync" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "setup_wizard.py"
        assert [Path(path).name for path in supplement.related_files] == ["advanced_step.py"]
        assert "disabled" in (supplement.systemic_impact or "")
        assert "Enable cloud sync" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_wizard_ui_ux_supplement_when_existing_issue_lacks_prerequisite_label(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "advanced_step.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "ui_ux",
                            "title": "Wizard dependency issue",
                            "description": "A later step contains disabled controls.",
                            "context_scope": "cross_file",
                            "related_files": ["src/advanced_step.py"],
                            "systemic_impact": "Users encounter disabled controls without enough explanation.",
                            "evidence_basis": "The advanced step disables controls when cloud sync is off.",
                        }
                    ],
                },
                {
                    "filename": "setup_wizard.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Wizard orientation issue",
                            "description": "The wizard does not show enough progress.",
                            "context_scope": "local",
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/setup_wizard.py'),
                'content': (
                    'from .advanced_step import AdvancedStep\n\n'
                    'class SetupWizard:\n'
                    '    def __init__(self):\n'
                    '        self.cloud_sync_enabled = tk.BooleanVar(value=False)\n'
                    '        tk.Checkbutton(self, text="Enable cloud sync", variable=self.cloud_sync_enabled)\n\n'
                    '    def open_advanced_step(self):\n'
                    '        AdvancedStep(self, cloud_sync_enabled=self.cloud_sync_enabled.get())\n'
                ),
                'filename': 'setup_wizard.py'
            },
            {
                'path': Path('/path/to/advanced_step.py'),
                'content': (
                    'class AdvancedStep:\n'
                    '    def __init__(self, master=None, *, cloud_sync_enabled=False):\n'
                    '        tk.Checkbutton(self, text="Sync in background", state="normal" if cloud_sync_enabled else "disabled")\n'
                ),
                'filename': 'advanced_step.py'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplements = [
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "Enable cloud sync" in (issue.evidence_basis or "")
        ]
        assert len(supplements) == 1

    def test_collect_review_issues_adds_local_busy_feedback_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "export_dialog.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "ui_ux",
                            "title": "Loading state missing",
                            "description": "The dialog does not show enough loading affordance.",
                            "context_scope": "local",
                        }
                    ],
                },
                {
                    "filename": "export_service.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Blocking export",
                            "description": "The export takes a while.",
                            "context_scope": "local",
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/export_dialog.py'),
                'content': (
                    'from .export_service import export_report\n\n'
                    'class ExportDialog:\n'
                    '    def start_export(self) -> None:\n'
                    '        self.status_var.set("Exporting...")\n'
                    '        export_report()\n'
                    '        self.status_var.set("Done")\n'
                ),
                'filename': 'export_dialog.py'
            },
            {
                'path': Path('/path/to/export_service.py'),
                'content': 'import time\n\ndef export_report() -> None:\n    time.sleep(5)\n',
                'filename': 'export_service.py'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "busy progress feedback" in issue.description.lower()
        )
        assert Path(supplement.file_path).name == "export_dialog.py"
        assert [Path(path).name for path in supplement.related_files] == ["export_service.py"]
        assert "confused" in (supplement.systemic_impact or "")
        assert "time.sleep(5)" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_loading_feedback_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "AccountPanel.tsx",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "ui_ux",
                            "title": "Missing loading state feedback",
                            "description": "The panel does not show enough loading feedback.",
                            "context_scope": "cross_file",
                            "related_files": ["src/useAccount.ts"],
                            "systemic_impact": "Users may perceive the panel as unresponsive.",
                        }
                    ],
                },
                {
                    "filename": "useAccount.ts",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Hook loading state",
                            "description": "The hook returns loading state.",
                            "context_scope": "local",
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/AccountPanel.tsx'),
                'content': (
                    'import { useAccount } from "./useAccount";\n\n'
                    'export function AccountPanel({ accountId }) {\n'
                    '  const { data, isLoading, error, refresh } = useAccount(accountId);\n'
                    '  if (!data) {\n'
                    '    return null;\n'
                    '  }\n'
                    '  return <button onClick={refresh}>Refresh</button>;\n'
                    '}\n'
                ),
                'filename': 'AccountPanel.tsx'
            },
            {
                'path': Path('/path/to/useAccount.ts'),
                'content': (
                    'export function useAccount(accountId) {\n'
                    '  return { data: null, isLoading: true, error: null, refresh: () => {} };\n'
                    '}\n'
                ),
                'filename': 'useAccount.ts'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "returns null when data is absent" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "AccountPanel.tsx"
        assert [Path(path).name for path in supplement.related_files] == ["useAccount.ts"]
        assert "confused" in (supplement.systemic_impact or "")
        assert "error: null" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_form_recovery_ui_ux_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "ProfileForm.tsx",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "ui_ux",
                            "title": "Missing feedback after form submission",
                            "description": "The form does not show enough post-submit feedback.",
                            "context_scope": "local",
                            "related_issues": [1],
                        },
                        {
                            "issue_id": "issue-0002",
                            "severity": "low",
                            "category": "ui_ux",
                            "title": "Form validation errors are not visually indicated",
                            "description": "The form uses a generic validation error state.",
                            "context_scope": "local",
                            "related_issues": [0],
                        },
                    ],
                },
                {
                    "filename": "validators.ts",
                    "findings": [
                        {
                            "issue_id": "issue-0003",
                            "severity": "low",
                            "category": "ui_ux",
                            "title": "Missing Empty State in ProfileForm",
                            "description": "The validator messages are not surfaced clearly.",
                            "context_scope": "local",
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/ProfileForm.tsx'),
                'content': (
                    'import { validateProfile } from "./validators";\n\n'
                    'async function handleSubmit(event) {\n'
                    '  const errors = validateProfile({ name, email });\n'
                    '  if (errors.length > 0) {\n'
                    '    setName("");\n'
                    '    setEmail("");\n'
                    '    setStatus("Profile could not be saved.");\n'
                    '    return;\n'
                    '  }\n'
                    '}\n'
                ),
                'filename': 'ProfileForm.tsx'
            },
            {
                'path': Path('/path/to/validators.ts'),
                'content': (
                    'export function validateProfile(payload) {\n'
                    '  const errors = [];\n'
                    '  if (!payload.name.trim()) {\n'
                    '    errors.push("Name is required.");\n'
                    '  }\n'
                    '  return errors;\n'
                    '}\n'
                ),
                'filename': 'validators.ts'
            },
        ]

        issues = collect_review_issues(target_files, ["ui_ux"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "generic" in issue.description.lower()
        )
        assert Path(supplement.file_path).name == "ProfileForm.tsx"
        assert [Path(path).name for path in supplement.related_files] == ["validators.ts"]
        assert "re-enter" in (supplement.systemic_impact or "")
        assert "validateProfile" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_false_success_error_handling_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "import_job.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "error_handling",
                            "title": "Swallowed Exception in Import Job",
                            "description": "The worker hides failures from callers.",
                            "context_scope": "local",
                            "evidence_basis": "The except block catches all exceptions and returns a success-looking result.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "import_controller.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "high",
                            "category": "error_handling",
                            "title": "Misleading Success Status in Import Controller",
                            "description": "The controller assumes completed means success.",
                            "context_scope": "cross_file",
                            "related_files": ["import_job.py"],
                            "systemic_impact": "Operators may be misled into believing the import worked.",
                            "evidence_basis": "The function assumes a success status based solely on 'status' being 'completed'.",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/import_controller.py'),
                'content': (
                    'from .import_job import run_import\n\n'
                    'def import_customers(upload: str) -> dict[str, object]:\n'
                    '    result = run_import(upload)\n'
                    '    if result["status"] == "completed":\n'
                    '        return {"message": "Import finished", "imported": result["count"]}\n'
                    '    return {"message": "Import failed"}\n'
                ),
                'filename': 'import_controller.py'
            },
            {
                'path': Path('/path/to/import_job.py'),
                'content': (
                    'def run_import(upload: str) -> dict[str, object]:\n'
                    '    try:\n'
                    '        rows = parse_csv(upload)\n'
                    '        return {"status": "completed", "count": len(rows)}\n'
                    '    except Exception:\n'
                    '        return {"status": "completed", "count": 0}\n'
                ),
                'filename': 'import_job.py'
            },
        ]

        issues = collect_review_issues(target_files, ["error_handling"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "except Exception" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "import_controller.py"
        assert [Path(path).name for path in supplement.related_files] == ["import_job.py"]
        assert "false success" in (supplement.systemic_impact or "").lower()
        assert "Import finished" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_retryless_timeout_error_handling_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "sync_worker.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "error_handling",
                            "title": "Missing Error Propagation to Callers",
                            "description": "The worker hides timeout detail.",
                            "context_scope": "local",
                            "evidence_basis": "The function catches TimeoutError and returns a failed status.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "sync_controller.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "high",
                            "category": "error_handling",
                            "title": "False Success State Returned After Upstream Error",
                            "description": "The controller disables sync on failure.",
                            "context_scope": "cross_file",
                            "related_files": ["sync_worker.py"],
                            "systemic_impact": "Operators may believe sync was disabled after a successful workflow.",
                            "evidence_basis": "The function checks only for failed status and disables the feature immediately.",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/sync_controller.py'),
                'content': (
                    'from .sync_worker import run_sync\n\n'
                    'def sync_now(batch_id: str) -> dict[str, object]:\n'
                    '    result = run_sync(batch_id)\n'
                    '    if result["status"] == "failed":\n'
                    '        disable_background_sync()\n'
                    '        return {"message": "Background sync disabled"}\n'
                    '    return {"message": "Sync finished"}\n'
                ),
                'filename': 'sync_controller.py'
            },
            {
                'path': Path('/path/to/sync_worker.py'),
                'content': (
                    'def run_sync(batch_id: str) -> dict[str, object]:\n'
                    '    try:\n'
                    '        push_sync_batch(batch_id)\n'
                    '        return {"status": "completed"}\n'
                    '    except TimeoutError:\n'
                    '        return {"status": "failed", "retryable": True, "reason": "timeout"}\n'
                ),
                'filename': 'sync_worker.py'
            },
        ]

        issues = collect_review_issues(target_files, ["error_handling"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "TimeoutError" in (issue.evidence_basis or "")
            and "retryable" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "sync_controller.py"
        assert [Path(path).name for path in supplement.related_files] == ["sync_worker.py"]
        assert "recovery" in (supplement.systemic_impact or "").lower()
        assert "Background sync disabled" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_inverted_window_data_validation_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "api.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "data_validation",
                            "title": "Missing Boundary Check on Time Window",
                            "description": "The API computes duration without checking ordering.",
                            "context_scope": "local",
                            "evidence_basis": "The function does not validate that start and end hours are correctly ordered.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "validation.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "info",
                            "category": "data_validation",
                            "title": "Type Coercion without Verification",
                            "description": "The validator only coerces the inputs.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from src.validation import validate_window\n\n'
                    'def create_maintenance_window(payload: dict) -> dict:\n'
                    '    validate_window(payload)\n'
                    '    duration_hours = int(payload["end_hour"]) - int(payload["start_hour"])\n'
                    '    return {"status": "scheduled", "duration_hours": duration_hours}\n'
                ),
                'filename': 'api.py'
            },
            {
                'path': Path('/path/to/validation.py'),
                'content': (
                    'def validate_window(payload: dict) -> None:\n'
                    '    if "start_hour" not in payload or "end_hour" not in payload:\n'
                    '        raise ValueError("Missing hour")\n'
                    '    int(payload["start_hour"])\n'
                    '    int(payload["end_hour"])\n'
                ),
                'filename': 'validation.py'
            },
        ]

        issues = collect_review_issues(target_files, ["data_validation"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "end_hour" in (issue.evidence_basis or "")
            and "validation.py" in " ".join(issue.related_files)
        )
        assert Path(supplement.file_path).name == "api.py"
        assert [Path(path).name for path in supplement.related_files] == ["validation.py"]
        assert "invalid" in (supplement.systemic_impact or "").lower()
        assert "start_hour" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_rollout_percent_range_data_validation_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "api.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "data_validation",
                            "title": "Runtime Uses Rollout Inputs Directly",
                            "description": "The API computes batch sizes from rollout inputs.",
                            "context_scope": "local",
                            "evidence_basis": "The function computes batch_size from payload fields after calling validate_rollout.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "validation.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "data_validation",
                            "title": "Integer Coercion Without Range Check",
                            "description": "The validator converts rollout_percent without bounding it.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from src.validation import validate_rollout\n\n'
                    'def create_rollout(payload: dict) -> dict:\n'
                    '    validate_rollout(payload)\n'
                    '    batch_size = int(payload["target_hosts"]) * int(payload["rollout_percent"]) // 100\n'
                    '    return {"status": "scheduled", "batch_size": batch_size}\n'
                ),
                'filename': 'api.py'
            },
            {
                'path': Path('/path/to/validation.py'),
                'content': (
                    'def validate_rollout(payload: dict) -> None:\n'
                    '    if "target_hosts" not in payload or "rollout_percent" not in payload:\n'
                    '        raise ValueError("Missing rollout field")\n'
                    '    int(payload["target_hosts"])\n'
                    '    int(payload["rollout_percent"])\n'
                ),
                'filename': 'validation.py'
            },
        ]

        issues = collect_review_issues(target_files, ["data_validation"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and "rollout_percent" in (issue.evidence_basis or "")
            and "validation.py" in " ".join(issue.related_files)
        )
        assert Path(supplement.file_path).name == "api.py"
        assert [Path(path).name for path in supplement.related_files] == ["validation.py"]
        assert "invalid" in (supplement.systemic_impact or "").lower()
        assert "0..100" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_rollout_percent_testing_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "validation.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "testability",
                            "title": "Validation Edge Cases Need Tests",
                            "description": "The validator has several untested edge cases.",
                            "context_scope": "local",
                            "evidence_basis": "The function has edge cases for values outside the accepted range.",
                            "related_issues": [1],
                        }
                    ],
                },
                {
                    "filename": "test_api.py",
                    "findings": [
                        {
                            "issue_id": "issue-0002",
                            "severity": "medium",
                            "category": "assertions",
                            "title": "Assertions Could Be Broader",
                            "description": "The happy-path assertion could check more details.",
                            "context_scope": "local",
                            "related_issues": [0],
                        }
                    ],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from src.validation import validate_rollout\n\n'
                    'def create_rollout(payload: dict) -> dict:\n'
                    '    validate_rollout(payload)\n'
                    '    batch_size = int(payload["target_hosts"]) * int(payload["rollout_percent"]) // 100\n'
                    '    return {"status": "scheduled", "batch_size": batch_size}\n'
                ),
                'filename': 'api.py'
            },
            {
                'path': Path('/path/to/validation.py'),
                'content': (
                    'def validate_rollout(payload: dict) -> None:\n'
                    '    if "target_hosts" not in payload or "rollout_percent" not in payload:\n'
                    '        raise ValueError("Missing rollout field")\n'
                    '    target_hosts = int(payload["target_hosts"])\n'
                    '    rollout_percent = int(payload["rollout_percent"])\n'
                    '    if target_hosts <= 0:\n'
                    '        raise ValueError("target_hosts must be positive")\n'
                    '    if rollout_percent < 0 or rollout_percent > 100:\n'
                    '        raise ValueError("rollout_percent must be between 0 and 100")\n'
                ),
                'filename': 'validation.py'
            },
            {
                'path': Path('/path/to/test_api.py'),
                'content': (
                    'import pytest\n\n'
                    'from src.api import create_rollout\n\n'
                    'def test_create_rollout_returns_batch_size_for_valid_payload() -> None:\n'
                    '    result = create_rollout({"target_hosts": "25", "rollout_percent": "40"})\n'
                    '    assert result == {"status": "scheduled", "batch_size": 10}\n\n'
                    'def test_create_rollout_rejects_missing_rollout_percent() -> None:\n'
                    '    with pytest.raises(ValueError, match="rollout_percent"):\n'
                    '        create_rollout({"target_hosts": "25"})\n'
                ),
                'filename': 'test_api.py'
            },
        ]

        issues = collect_review_issues(target_files, ["testing"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and issue.issue_type == "testing"
            and "rollout_percent" in (issue.evidence_basis or "")
            and "validation.py" in " ".join(issue.related_files)
        )
        assert Path(supplement.file_path).name == "test_api.py"
        assert [Path(path).name for path in supplement.related_files] == ["validation.py"]
        assert "regress" in (supplement.systemic_impact or "").lower()
        assert "0..100" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_default_sync_disabled_regression_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "settings_defaults.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "medium",
                            "category": "behavioral change",
                            "title": "Sync default changed",
                            "description": "The sync default changed from true to false.",
                            "context_scope": "local",
                            "evidence_basis": "sync_enabled changed from true to false.",
                        }
                    ],
                }
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/settings_defaults.py'),
                'content': (
                    'def load_default_preferences() -> dict:\n'
                    '    return {\n'
                    '        "sync_enabled": False,\n'
                    '        "sync_interval_minutes": 15,\n'
                    '    }\n'
                ),
                'filename': 'settings_defaults.py'
            },
        ]

        with patch('aicodereviewer.reviewer._read_file_content') as mock_read:
            def _read_side_effect(path):
                if Path(path).name == 'settings_defaults.py':
                    return (
                        'def load_default_preferences() -> dict:\n'
                        '    return {\n'
                        '        "sync_enabled": False,\n'
                        '        "sync_interval_minutes": 15,\n'
                        '    }\n'
                    )
                if Path(path).name == 'app_startup.py':
                    return (
                        'from src.settings_defaults import load_default_preferences\n\n'
                        'def initialize_sync(sync_scheduler) -> None:\n'
                        '    preferences = load_default_preferences()\n'
                        '    if preferences["sync_enabled"]:\n'
                        '        sync_scheduler.start()\n'
                    )
                return ''

            mock_read.side_effect = _read_side_effect

            with patch('pathlib.Path.exists', return_value=True):
                issues = collect_review_issues(target_files, ["regression"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and issue.issue_type == "regression"
            and "sync_enabled" in (issue.evidence_basis or "")
            and "app_startup.py" in " ".join(issue.related_files)
        )
        assert Path(supplement.file_path).name == "settings_defaults.py"
        assert [Path(path).name for path in supplement.related_files] == ["app_startup.py"]
        assert "disabled" in (supplement.systemic_impact or "").lower()
        assert "sync_enabled" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_inverted_sync_start_guard_regression_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "app_startup.py",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "regression",
                            "title": "Sync Scheduler Start Condition Changed",
                            "description": "The condition for starting the sync scheduler has been unintentionally inverted.",
                            "context_scope": "local",
                            "systemic_impact": "Existing startup flows may no longer run sync scheduler tasks if sync_enabled was previously true.",
                            "evidence_basis": "The original condition checked for preferences[\"sync_enabled\"] being True before starting the sync scheduler. The current implementation checks for it being False.",
                        }
                    ],
                }
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/app_startup.py'),
                'content': (
                    'from src.settings_defaults import load_default_preferences\n\n'
                    'def initialize_sync(sync_scheduler) -> None:\n'
                    '    preferences = load_default_preferences()\n'
                    '    if not preferences["sync_enabled"]:\n'
                    '        sync_scheduler.start()\n'
                ),
                'filename': 'app_startup.py'
            },
        ]

        with patch('aicodereviewer.reviewer._read_file_content') as mock_read:
            def _read_side_effect(path):
                if Path(path).name == 'app_startup.py':
                    return (
                        'from src.settings_defaults import load_default_preferences\n\n'
                        'def initialize_sync(sync_scheduler) -> None:\n'
                        '    preferences = load_default_preferences()\n'
                        '    if not preferences["sync_enabled"]:\n'
                        '        sync_scheduler.start()\n'
                    )
                if Path(path).name == 'settings_defaults.py':
                    return (
                        'def load_default_preferences() -> dict:\n'
                        '    return {\n'
                        '        "sync_enabled": True,\n'
                        '        "sync_interval_minutes": 15,\n'
                        '    }\n'
                    )
                return ''

            mock_read.side_effect = _read_side_effect

            with patch('pathlib.Path.exists', return_value=True):
                issues = collect_review_issues(target_files, ["regression"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "cross_file"
            and issue.issue_type == "regression"
            and "sync_enabled" in (issue.evidence_basis or "")
            and "settings_defaults.py" in " ".join(issue.related_files)
        )
        assert Path(supplement.file_path).name == "app_startup.py"
        assert [Path(path).name for path in supplement.related_files] == ["settings_defaults.py"]
        assert "disabled" in (supplement.systemic_impact or "").lower()
        assert "guard" in supplement.description.lower()

    def test_collect_review_issues_includes_readme_for_documentation_reviews(self, tmp_path):
        project_root = tmp_path / "project"
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True)
        readme_path = project_root / "README.md"
        cli_path = src_dir / "cli.py"
        readme_path.write_text("Use syncctl run --dry-run", encoding="utf-8")
        cli_path.write_text("def main():\n    return 'ok'\n", encoding="utf-8")

        mock_client = MagicMock()
        mock_client.set_project_context = MagicMock()
        mock_client.set_detected_frameworks = MagicMock()

        captured_batch = {}

        def _capture_batch(batch, review_type, client, lang, spec_content=None, cancel_check=None):
            captured_batch["review_type"] = review_type
            captured_batch["names"] = [
                Path(str(item)).name if not isinstance(item, dict)
                else Path(str(item["path"])).name
                for item in batch
            ]
            return []

        with patch('aicodereviewer.reviewer._process_file_batch', side_effect=_capture_batch):
            issues = collect_review_issues([cli_path], ["documentation"], mock_client, "en")

        assert issues == []
        assert captured_batch["review_type"] == "documentation"
        assert captured_batch["names"] == ["cli.py", "README.md"]

    def test_collect_review_issues_includes_pyproject_for_dependency_reviews(self, tmp_path):
        project_root = tmp_path / "project"
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True)
        pyproject_path = project_root / "pyproject.toml"
        module_path = src_dir / "config_writer.py"
        pyproject_path.write_text("[project]\nname='demo'\ndependencies=['requests']\n", encoding="utf-8")
        module_path.write_text("import yaml\n", encoding="utf-8")

        mock_client = MagicMock()
        mock_client.set_project_context = MagicMock()
        mock_client.set_detected_frameworks = MagicMock()

        captured_batch = {}

        def _capture_batch(batch, review_type, client, lang, spec_content=None, cancel_check=None):
            captured_batch["review_type"] = review_type
            captured_batch["names"] = [
                Path(str(item)).name if not isinstance(item, dict)
                else Path(str(item["path"])).name
                for item in batch
            ]
            return []

        with patch('aicodereviewer.reviewer._process_file_batch', side_effect=_capture_batch):
            issues = collect_review_issues([module_path], ["dependency"], mock_client, "en")

        assert issues == []
        assert captured_batch["review_type"] == "dependency"
        assert sorted(captured_batch["names"]) == ["config_writer.py", "pyproject.toml"]

    def test_collect_review_issues_includes_license_files_for_license_reviews(self, tmp_path):
        project_root = tmp_path / "project"
        src_dir = project_root / "src"
        src_dir.mkdir(parents=True)
        license_path = project_root / "LICENSE"
        notices_path = project_root / "THIRD_PARTY_NOTICES.md"
        inventory_path = project_root / "licenses_check.csv"
        pyproject_path = project_root / "pyproject.toml"
        module_path = src_dir / "report_export.py"
        license_path.write_text("MIT License\n", encoding="utf-8")
        notices_path.write_text("All dependencies are permissive and compatible with MIT.\n", encoding="utf-8")
        inventory_path.write_text("name,version,license\nnetworksync,1.2.0,AGPL-3.0-only\n", encoding="utf-8")
        pyproject_path.write_text("[project]\nname='demo'\ndependencies=['networksync>=1.2']\n", encoding="utf-8")
        module_path.write_text("import networksync\n", encoding="utf-8")

        mock_client = MagicMock()
        mock_client.set_project_context = MagicMock()
        mock_client.set_detected_frameworks = MagicMock()

        captured_batch = {}

        def _capture_batch(batch, review_type, client, lang, spec_content=None, cancel_check=None):
            captured_batch["review_type"] = review_type
            captured_batch["names"] = [
                Path(str(item)).name if not isinstance(item, dict)
                else Path(str(item["path"])).name
                for item in batch
            ]
            return []

        with patch('aicodereviewer.reviewer._process_file_batch', side_effect=_capture_batch):
            issues = collect_review_issues([module_path], ["license"], mock_client, "en")

        assert issues == []
        assert captured_batch["review_type"] == "license"
        assert sorted(captured_batch["names"]) == [
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "licenses_check.csv",
            "pyproject.toml",
            "report_export.py",
        ]

    def test_collect_review_issues_adds_local_dialog_semantics_accessibility_supplement(self, tmp_path):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "SettingsModal.tsx",
                    "findings": [
                        {
                            "issue_id": "issue-0001",
                            "severity": "high",
                            "category": "accessibility",
                            "title": "Missing accessible name for button",
                            "description": "The Close button lacks an accessible name.",
                            "context_scope": "local",
                            "systemic_impact": "Screen reader users may struggle to operate the modal.",
                            "evidence_basis": "Button element lacks aria-label or text content.",
                        }
                    ],
                }
            ],
        })

        modal_path = tmp_path / "SettingsModal.tsx"
        modal_path.write_text(
            'type SettingsModalProps = {\n'
            '  isOpen: boolean;\n'
            '  onClose: () => void;\n'
            '};\n\n'
            'export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {\n'
            '  if (!isOpen) {\n'
            '    return null;\n'
            '  }\n\n'
            '  return (\n'
            '    <div className="modal-backdrop" onClick={onClose}>\n'
            '      <div className="modal-panel" onClick={(event) => event.stopPropagation()}>\n'
            '        <h2>Sync settings</h2>\n'
            '        <p>Choose how often the desktop app checks for updates.</p>\n'
            '        <button type="button" onClick={onClose}>Close</button>\n'
            '      </div>\n'
            '    </div>\n'
            '  );\n'
            '}\n',
            encoding="utf-8",
        )

        target_files: List[FileInfo] = [modal_path]  # type: ignore[list-item]

        issues = collect_review_issues(target_files, ["accessibility"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.context_scope == "local"
            and issue.issue_type == "accessibility"
            and "dialog" in issue.description.lower()
            and "role" in (issue.evidence_basis or "").lower()
        )
        assert Path(supplement.file_path).name == "SettingsModal.tsx"
        assert "screen" in (supplement.systemic_impact or "").lower()
        assert "aria-modal" in (supplement.evidence_basis or "").lower()

    def test_collect_review_issues_adds_local_shell_command_injection_security_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {"filename": "api.py", "findings": []},
                {"filename": "report_export.py", "findings": []},
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from .report_export import run_export\n\n'
                    'def export_activity_report(request, current_user):\n'
                    '    output_path = request["output_path"]\n'
                    '    output_format = request.get("format", "csv")\n'
                    '    return run_export(\n'
                    '        username=current_user["username"],\n'
                    '        output_format=output_format,\n'
                    '        output_path=output_path,\n'
                    '    )\n'
                ),
                'filename': 'api.py'
            },
            {
                'path': Path('/path/to/report_export.py'),
                'content': (
                    'import subprocess\n\n'
                    'def run_export(*, username, output_format, output_path):\n'
                    '    command = f"generate-report --user {username} --format {output_format} --output {output_path}"\n'
                    '    completed = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)\n'
                    '    return completed.returncode == 0\n'
                ),
                'filename': 'report_export.py'
            },
        ]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.issue_type == "security"
            and issue.context_scope == "cross_file"
            and "shell=true" in (issue.evidence_basis or "").lower()
        )
        assert Path(supplement.file_path).name == "report_export.py"
        assert [Path(path).name for path in supplement.related_files] == ["api.py"]
        assert "arbitrary command" in (supplement.systemic_impact or "").lower()

    def test_collect_review_issues_adds_local_dead_code_unreachable_fallback_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [{
                "filename": "formatter.py",
                "findings": [{
                    "issue_id": "issue-0001",
                    "severity": "medium",
                    "category": "dead_code",
                    "title": "Unused Feature Flag",
                    "description": "The feature flag is permanently false.",
                    "context_scope": "local",
                    "evidence_basis": "USE_LEGACY_RENDERER is set to False.",
                }],
            }],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/formatter.py'),
                'content': (
                    'USE_LEGACY_RENDERER = False\n\n'
                    'def render_invoice(payload):\n'
                    '    if USE_LEGACY_RENDERER:\n'
                    '        return _render_legacy_invoice(payload)\n'
                    '    return _render_modern_invoice(payload)\n\n'
                    'def _render_legacy_invoice(payload):\n'
                    '    return payload\n'
                ),
                'filename': 'formatter.py'
            },
        ]

        issues = collect_review_issues(target_files, ["dead_code"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.issue_type == "dead_code"
            and "unreachable legacy fallback" in issue.description.lower()
        )
        assert Path(supplement.file_path).name == "formatter.py"
        assert supplement.context_scope == "local"
        assert "obsolete" in (supplement.systemic_impact or "")
        assert "USE_LEGACY_RENDERER" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_dead_code_stale_feature_flag_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "toolbar.py",
                    "findings": [{
                        "issue_id": "issue-0001",
                        "severity": "medium",
                        "category": "dead_code",
                        "title": "Unreachable Branch due to Stale Feature Flag",
                        "description": "The branch never runs.",
                        "context_scope": "cross_file",
                        "related_files": ["feature_flags.py"],
                        "evidence_basis": "ENABLE_BULK_ARCHIVE is set to False in feature_flags.py.",
                    }],
                },
                {
                    "filename": "feature_flags.py",
                    "findings": [{
                        "issue_id": "issue-0002",
                        "severity": "medium",
                        "category": "dead_code",
                        "title": "Dormant Feature Flag",
                        "description": "The flag is false.",
                        "context_scope": "cross_file",
                        "related_files": ["toolbar.py"],
                    }],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/feature_flags.py'),
                'content': 'ENABLE_BULK_ARCHIVE = False\n',
                'filename': 'feature_flags.py'
            },
            {
                'path': Path('/path/to/toolbar.py'),
                'content': (
                    'from .feature_flags import ENABLE_BULK_ARCHIVE\n\n'
                    'class MessageToolbar:\n'
                    '    def build_actions(self):\n'
                    '        actions = [("Refresh", self._handle_refresh)]\n'
                    '        if ENABLE_BULK_ARCHIVE:\n'
                    '            actions.append(("Bulk archive", self._handle_bulk_archive))\n'
                    '        return actions\n\n'
                    '    def _handle_bulk_archive(self):\n'
                    '        self._open_bulk_archive_dialog()\n'
                ),
                'filename': 'toolbar.py'
            },
        ]

        issues = collect_review_issues(target_files, ["dead_code"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.issue_type == "dead_code"
            and "obsolete" in (issue.systemic_impact or "").lower()
            and "ENABLE_BULK_ARCHIVE" in (issue.evidence_basis or "")
        )
        assert Path(supplement.file_path).name == "toolbar.py"
        assert [Path(path).name for path in supplement.related_files] == ["feature_flags.py"]
        assert "obsolete" in (supplement.systemic_impact or "")
        assert "ENABLE_BULK_ARCHIVE" in (supplement.evidence_basis or "")

    def test_collect_review_issues_adds_local_dead_code_obsolete_compat_shim_supplement(self):
        mock_client = MagicMock()
        mock_client._backend_kind = "local"
        mock_client.get_review.return_value = json.dumps({
            "files": [
                {
                    "filename": "legacy_export.py",
                    "findings": [{
                        "issue_id": "issue-0001",
                        "severity": "medium",
                        "category": "dead_code",
                        "title": "Obsolete Legacy Export Function",
                        "description": "Legacy export code is no longer used.",
                        "context_scope": "cross_file",
                        "related_files": ["api.py"],
                        "evidence_basis": "render_legacy_csv looks unused.",
                    }],
                },
                {
                    "filename": "report_service.py",
                    "findings": [{
                        "issue_id": "issue-0002",
                        "severity": "medium",
                        "category": "dead_code",
                        "title": "Dormant Report Generation Dependency",
                        "description": "Modern export code may be unused.",
                        "context_scope": "cross_file",
                    }],
                },
            ],
        })

        target_files: List[FileInfo] = [  # type: ignore[list-item]
            {
                'path': Path('/path/to/api.py'),
                'content': (
                    'from .report_service import generate_report\n\n'
                    'def handle_request(customer_id):\n'
                    '    return generate_report(customer_id)\n'
                ),
                'filename': 'api.py'
            },
            {
                'path': Path('/path/to/report_service.py'),
                'content': (
                    'from .modern_export import render_modern_csv\n\n'
                    'def generate_report(customer_id):\n'
                    '    return render_modern_csv(customer_id)\n'
                ),
                'filename': 'report_service.py'
            },
            {
                'path': Path('/path/to/legacy_export.py'),
                'content': (
                    'LEGACY_EXPORT_ENABLED = False\n\n'
                    'def render_legacy_csv(customer_id):\n'
                    '    return _legacy_header(customer_id)\n\n'
                    'def _legacy_header(customer_id):\n'
                    '    return customer_id\n'
                ),
                'filename': 'legacy_export.py'
            },
            {
                'path': Path('/path/to/modern_export.py'),
                'content': 'def render_modern_csv(customer_id):\n    return customer_id\n',
                'filename': 'modern_export.py'
            },
        ]

        issues = collect_review_issues(target_files, ["dead_code"], mock_client, "en")

        supplement = next(
            issue for issue in issues
            if issue.issue_type == "dead_code"
            and "compatibility shim" in issue.description.lower()
        )
        assert Path(supplement.file_path).name == "legacy_export.py"
        assert [Path(path).name for path in supplement.related_files] == ["report_service.py", "api.py"]
        assert "obsolete" in (supplement.systemic_impact or "")
        assert "render_legacy_csv" in (supplement.evidence_basis or "")

    def test_collect_review_issues_file_read_error(self):
        """Test handling file read errors"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Issues found"

        target_files: List[FileInfo] = [Path("/nonexistent/file.py")]  # type: ignore[list-item]

        issues = collect_review_issues(target_files, ["security"], mock_client, "en")

        assert len(issues) == 0

    def test_collect_review_issues_progress_callback(self):
        """Test that progress callback is invoked."""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Some feedback"

        target_files: List[FileInfo] = [{  # type: ignore[list-item]
            'path': Path("/path/to/test.py"),
            'content': "print('code')",
            'filename': 'test.py'
        }]
        cb = MagicMock()

        collect_review_issues(target_files, ["security"], mock_client, "en", progress_callback=cb)

        cb.assert_called()


class TestVerifyIssueResolved:
    """Test issue resolution verification functionality"""

    def test_verify_issue_resolved_success(self):
        """Test successful issue resolution verification"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "No issues found"

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Long detailed feedback about security issues" * 10
        )

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "fixed code"
            result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is True

    def test_verify_issue_resolved_still_issues(self):
        """Test when issues are still present"""
        mock_client = MagicMock()
        mock_client.get_review.return_value = "Still has security issues"

        issue = ReviewIssue(
            file_path="/path/to/test.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Short feedback"
        )

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "modified code"
            result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is False

    def test_verify_issue_resolved_file_error(self):
        """Test handling file read errors during verification"""
        mock_client = MagicMock()

        issue = ReviewIssue(
            file_path="/nonexistent/file.py",
            issue_type="security",
            severity="high",
            description="Test issue",
            code_snippet="old code",
            ai_feedback="Some feedback"
        )

        result = verify_issue_resolved(issue, mock_client, "security", "en")

        assert result is False
