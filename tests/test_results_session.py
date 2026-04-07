from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from aicodereviewer.execution import DeferredReportState, ReviewSessionState
from aicodereviewer.execution.models import SESSION_PAYLOAD_VERSION, SESSION_REPORT_CONTEXT_KEY
from aicodereviewer.gui.results_mixin import ResultsTabMixin
from aicodereviewer.models import ReviewIssue


class _DummyWidget:
    def __init__(self) -> None:
        self.configured: dict[str, object] = {}
        self.destroyed = False

    def configure(self, **kwargs) -> None:
        self.configured.update(kwargs)

    def destroy(self) -> None:
        self.destroyed = True


class _DummyFrame:
    def __init__(self, children=None) -> None:
        self._children = list(children or [])

    def winfo_children(self):
        return list(self._children)


class _DummyStatusVar:
    def __init__(self) -> None:
        self.value = None

    def set(self, value: str) -> None:
        self.value = value


class _DummyResultsApp(ResultsTabMixin):
    def __init__(self, session_path: Path) -> None:
        self._path = session_path
        self._issues: list[ReviewIssue] = []
        self._issue_cards: list[dict[str, object]] = []
        self._session_runner = None
        self._testing_mode = False
        self.results_summary = _DummyWidget()
        self.review_changes_btn = _DummyWidget()
        self.finalize_btn = _DummyWidget()
        self.save_session_btn = _DummyWidget()
        self.results_frame = _DummyFrame([_DummyWidget()])
        self.status_var = _DummyStatusVar()
        self.toasts: list[tuple[str, bool]] = []
        self.shown_issues: list[ReviewIssue] = []

    @property
    def _session_path(self) -> Path:
        return self._path

    def _current_session_runner(self):
        return getattr(self, "_session_runner", None)

    def _bind_session_runner(self, runner) -> None:
        self._session_runner = runner

    def _clear_session_runner(self) -> None:
        self._session_runner = None

    def _show_toast(self, message: str, *, duration: int = 6000, error: bool = False) -> None:
        self.toasts.append((message, error))

    def _show_issues(self, issues: list[ReviewIssue]):
        self.shown_issues = list(issues)
        self._issue_cards = [{"issue": issue} for issue in issues]


def _runner_with_report_context(meta: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        serialized_report_context=dict(meta),
        session_state=ReviewSessionState.from_report_context(dict(meta)),
    )


def test_save_and_load_session_round_trips_report_context(monkeypatch, tmp_path: Path):
    session_path = tmp_path / 'session.json'
    app = _DummyResultsApp(session_path)
    issue = ReviewIssue(
        file_path='a.py',
        issue_type='security',
        description='x',
        status='resolved',
        resolution_reason='Applied after review',
        resolution_provenance='ai_edited',
        ai_fix_suggested='unsafe()\n',
        ai_fix_applied='safe()\n',
    )
    app._issues = [issue]
    app._bind_session_runner(_runner_with_report_context({
        'project_path': 'proj',
        'review_types': ['security'],
        'scope': 'project',
        'total_files_scanned': 1,
        'language': 'en',
        'diff_source': None,
        'programmers': ['Alice'],
        'reviewers': ['Bob'],
        'backend': 'local',
    }))

    app._save_session()

    saved_payload = json.loads(session_path.read_text(encoding='utf-8'))
    assert saved_payload["format_version"] == SESSION_PAYLOAD_VERSION
    assert saved_payload[SESSION_REPORT_CONTEXT_KEY]["backend"] == 'local'
    assert saved_payload["issues"][0]["resolution_provenance"] == 'ai_edited'
    assert saved_payload["issues"][0]["ai_fix_suggested"] == 'unsafe()\n'
    assert saved_payload["issues"][0]["ai_fix_applied"] == 'safe()\n'

    app._issues = []
    app._clear_session_runner()

    monkeypatch.setattr('aicodereviewer.gui.results_mixin.filedialog.askopenfilename', lambda **_: str(session_path))
    monkeypatch.setattr('aicodereviewer.gui.results_mixin.messagebox.showerror', lambda *args, **kwargs: None)

    app._load_session()

    runner = app._current_session_runner()

    assert len(app.shown_issues) == 1
    assert app.shown_issues[0].resolution_provenance == 'ai_edited'
    assert app.shown_issues[0].ai_fix_suggested == 'unsafe()\n'
    assert app.shown_issues[0].ai_fix_applied == 'safe()\n'
    assert runner is not None
    meta = runner.serialized_report_context
    assert meta['backend'] == 'local'
    assert meta['project_path'] == 'proj'
    assert runner.last_execution is not None
    assert runner.last_execution.status == 'issues_found'
    assert runner.last_job is not None
    assert runner.last_job.state == 'awaiting_gui_finalize'


def test_finalize_without_report_context_preserves_loaded_issues() -> None:
    app = _DummyResultsApp(Path('session.json'))
    issue = ReviewIssue(file_path='a.py', issue_type='security', description='x')
    app._issues = [issue]
    app._issue_cards = [{"issue": issue}]

    app._do_finalize()

    assert app._issues == [issue]
    assert len(app._issue_cards) == 1
    assert app.results_summary.configured == {}
    assert app.toasts and app.toasts[-1][1] is True


def test_load_session_rejects_file_outside_workspace_or_config(monkeypatch, tmp_path: Path) -> None:
    session_path = tmp_path / 'session.json'
    app = _DummyResultsApp(session_path)
    external_session = tmp_path.parent / 'outside-session.json'
    external_session.write_text(json.dumps({"issues": []}), encoding='utf-8')

    errors: list[str] = []
    monkeypatch.setattr('aicodereviewer.gui.results_mixin.filedialog.askopenfilename', lambda **_: str(external_session))
    monkeypatch.setattr(
        'aicodereviewer.gui.results_mixin.messagebox.showerror',
        lambda _title, message: errors.append(str(message)),
    )

    app._load_session()

    assert errors
    assert 'Session file must stay within the workspace or config directory' in errors[0]
    assert app._current_session_runner() is None
    assert app.shown_issues == []


def test_load_session_rejects_issue_file_path_outside_workspace(monkeypatch, tmp_path: Path) -> None:
    session_path = tmp_path / 'session.json'
    app = _DummyResultsApp(session_path)
    session_path.write_text(
        json.dumps(
            {
                'format_version': SESSION_PAYLOAD_VERSION,
                'saved_at': '2026-04-06T00:00:00',
                'issues': [
                    {
                        'file_path': str(tmp_path.parent / 'outside.py'),
                        'issue_type': 'security',
                        'description': 'outside path',
                    }
                ],
                SESSION_REPORT_CONTEXT_KEY: None,
            }
        ),
        encoding='utf-8',
    )

    errors: list[str] = []
    monkeypatch.setattr('aicodereviewer.gui.results_mixin.filedialog.askopenfilename', lambda **_: str(session_path))
    monkeypatch.setattr(
        'aicodereviewer.gui.results_mixin.messagebox.showerror',
        lambda _title, message: errors.append(str(message)),
    )

    app._load_session()

    assert errors
    assert 'Session payload file paths must stay within the expected session roots' in errors[0]
    assert app._current_session_runner() is None
    assert app.shown_issues == []