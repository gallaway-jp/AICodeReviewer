from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
        self._review_runner = None
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

    def _show_toast(self, message: str, *, duration: int = 6000, error: bool = False) -> None:
        self.toasts.append((message, error))

    def _show_issues(self, issues: list[ReviewIssue]):
        self.shown_issues = list(issues)
        self._issue_cards = [{"issue": issue} for issue in issues]


def test_save_and_load_session_round_trips_report_metadata(monkeypatch, tmp_path: Path):
    session_path = tmp_path / 'session.json'
    app = _DummyResultsApp(session_path)
    issue = ReviewIssue(file_path='a.py', issue_type='security', description='x')
    app._issues = [issue]
    app._review_runner = SimpleNamespace(_pending_report_meta={
        'project_path': 'proj',
        'review_types': ['security'],
        'scope': 'project',
        'total_files_scanned': 1,
        'language': 'en',
        'diff_source': None,
        'programmers': ['Alice'],
        'reviewers': ['Bob'],
        'backend': 'local',
    })

    app._save_session()

    app._issues = []
    app._review_runner = None

    monkeypatch.setattr('aicodereviewer.gui.results_mixin.filedialog.askopenfilename', lambda **_: str(session_path))
    monkeypatch.setattr('aicodereviewer.gui.results_mixin.messagebox.showerror', lambda *args, **kwargs: None)

    app._load_session()

    assert len(app.shown_issues) == 1
    assert app._review_runner is not None
    assert app._review_runner._pending_report_meta['backend'] == 'local'
    assert app._review_runner._pending_report_meta['project_path'] == 'proj'


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