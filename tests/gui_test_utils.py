from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from aicodereviewer.i18n import t


class QueuePanelHarness:
    """Test-facing helper for the Review tab queue panel."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def _coordinator(self) -> Any:
        return getattr(self.app, "_review_submission_queue")

    def _widgets(self) -> Any:
        widgets = getattr(self._coordinator(), "_widgets", None)
        if widgets is None:
            raise AssertionError("Queue panel widgets are not bound")
        return widgets

    def _ordered_snapshots(self) -> list[Any]:
        coordinator = self._coordinator()
        return list(
            coordinator.presenter.order_snapshots(
                coordinator.scheduler.list_submission_snapshots()
            )
        )

    def snapshots(self) -> list[Any]:
        return list(self._coordinator().scheduler.list_submission_snapshots())

    def active_submission_id(self) -> int | None:
        return self._coordinator().scheduler.active_submission_id

    def selected_submission_id(self) -> int | None:
        return self._coordinator().selection.submission_id

    def is_bound(self) -> bool:
        return getattr(self._coordinator(), "_widgets", None) is not None

    def display_labels(self) -> list[str]:
        menu = self._widgets().menu
        try:
            values = menu.cget("values")
        except Exception:
            values = getattr(menu, "_values", ())
        return list(values)

    def selected_label(self) -> str:
        variable = self._widgets().variable
        if hasattr(variable, "get"):
            return str(variable.get())
        return str(getattr(variable, "value", ""))

    def summary_text(self) -> str:
        return str(self._widgets().summary_label.cget("text"))

    def detail_text(self) -> str:
        return str(self._widgets().detail_label.cget("text"))

    def labels(self) -> dict[str, int]:
        return {
            label: snapshot.submission_id
            for label, snapshot in zip(self.display_labels(), self._ordered_snapshots())
        }

    def display_ids(self) -> list[int]:
        return list(self.labels().values())

    def label_for_submission(self, submission_id: int) -> str:
        for label, current_submission_id in self.labels().items():
            if current_submission_id == submission_id:
                return label
        raise AssertionError(f"Submission id {submission_id} is not visible in the queue panel")

    def select_submission(self, submission_id: int) -> None:
        label = self.label_for_submission(submission_id)
        menu = self._widgets().menu
        self._widgets().variable.set(label)
        command = getattr(menu, "_command", None)
        if callable(command):
            command(label)
            return
        raise AssertionError("Queue option menu does not expose an invokable command callback")

    def invoke_cancel(self) -> None:
        self._widgets().cancel_button.invoke()


class StatusBarHarness:
    """Test-facing helper for the app status bar."""

    def __init__(self, app: Any, wait_until: Any) -> None:
        self.app = app
        self._wait_until = wait_until

    def text(self) -> str:
        return str(self.app.status_var.get())

    def wait_for_text(
        self,
        expected_text: str,
        *,
        timeout: float = 5.0,
        message: str | None = None,
    ) -> None:
        self._wait_until(
            lambda: self.text() == expected_text,
            timeout=timeout,
            message=message or f"Status never became {expected_text!r}",
        )


class ReviewRuntimeHarness:
    """Test-facing helper for the active review runtime state."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def is_running(self) -> bool:
        return bool(self.app._is_review_execution_running())

    def is_review_changes_running(self) -> bool:
        return bool(self.app._is_review_changes_running())

    def current_runner(self) -> Any:
        return self.app._current_session_runner()

    def active_runner(self) -> Any:
        return self.app._active_review.runner

    def active_client(self) -> Any:
        return self.app._active_review.client

    def cancel_event(self) -> Any:
        return self.app._active_review.cancel_event

    def controller_running(self) -> bool:
        return bool(self.app._active_review.running)

    def progress_message(self) -> str | None:
        return self.app._active_review.progress_message

    def progress_current(self) -> int:
        return int(self.app._active_review.progress_current)

    def progress_total(self) -> int:
        return int(self.app._active_review.progress_total)

    def elapsed_started_at(self) -> float | None:
        return self.app._active_review.elapsed_started_at

    def elapsed_after_id(self) -> str | None:
        return self.app._active_review.elapsed_after_id


class ResultsTabHarness:
    """Test-facing helper for Results tab issue-list and action state."""

    def __init__(self, app: Any, wait_until: Any) -> None:
        self.app = app
        self._wait_until = wait_until

    def current_tab(self) -> str:
        return str(self.app.tabs.get())

    def show_issues(self, issues: list[Any]) -> None:
        self.app._show_issues(issues)

    def issues(self) -> list[Any]:
        return list(getattr(self.app, "_issues"))

    def issue_count(self) -> int:
        return len(getattr(self.app, "_issue_cards"))

    def visible_issue_count(self) -> int:
        return sum(
            1
            for record in getattr(self.app, "_issue_cards")
            if record["card"].winfo_manager() != ""
        )

    def issue_descriptions(self) -> list[str]:
        return [str(issue.description) for issue in self.issues()]

    def card(self, index: int) -> Any:
        return getattr(self.app, "_issue_cards")[index]

    def selected_cards(self, indexes: list[int] | None = None) -> list[tuple[int, Any]]:
        issue_cards = getattr(self.app, "_issue_cards")
        if indexes is None:
            indexes = list(range(len(issue_cards)))
        return [(index, issue_cards[index]) for index in indexes]

    def show_batch_fix_popup(
        self,
        results: dict[int, Any],
        *,
        selected_indexes: list[int] | None = None,
    ) -> None:
        self.app._show_batch_fix_popup(self.selected_cards(selected_indexes), results)

    def enter_ai_fix_mode(self) -> None:
        self.app.ai_fix_mode_btn.invoke()

    def start_ai_fix(self) -> None:
        self.app.start_ai_fix_btn.invoke()

    def cancel_ai_fix(self) -> None:
        self.app.cancel_ai_fix_btn.invoke()

    def ai_fix_mode_button_state(self) -> str:
        return str(self.app.ai_fix_mode_btn.cget("state"))

    def ai_fix_mode_button_visible(self) -> bool:
        return self.app.ai_fix_mode_btn.winfo_manager() != ""

    def is_ai_fix_mode_active(self) -> bool:
        return bool(getattr(self.app, "_ai_fix_mode", False))

    def is_ai_fix_running(self) -> bool:
        return bool(self.app._is_ai_fix_running())

    def ai_fix_runtime_running(self) -> bool:
        return bool(self.app._active_ai_fix.running)

    def ai_fix_cancel_event(self) -> Any:
        return self.app._active_ai_fix_cancel_event()

    def ai_fix_runtime_client(self) -> Any:
        return self.app._active_ai_fix.client

    def active_review_client(self) -> Any:
        return self.app._active_review_client()

    def is_busy(self) -> bool:
        return bool(self.app._is_busy())

    def ai_fix_cancel_button_text(self) -> str:
        return str(self.app.cancel_ai_fix_btn.cget("text"))

    def wait_until_ai_fix_stops(
        self,
        *,
        timeout: float = 5.0,
        message: str | None = None,
    ) -> None:
        self._wait_until(
            lambda: not self.is_ai_fix_running(),
            timeout=timeout,
            message=message or "AI Fix did not stop before timeout",
        )

    def finalize_state(self) -> str:
        return str(self.app.finalize_btn.cget("state"))

    def save_session_state(self) -> str:
        return str(self.app.save_session_btn.cget("state"))

    def filter_count_text(self) -> str:
        return str(self.app._filter_count_lbl.cget("text"))

    def set_severity_filter(self, value: str) -> None:
        self.app._filter_sev_var.set(value)

    def set_status_filter(self, value: str) -> None:
        self.app._filter_status_var.set(value)

    def set_type_filter(self, value: str) -> None:
        self.app._filter_type_var.set(value)

    def apply_filters(self) -> None:
        self.app._apply_filters()

    def clear_filters(self) -> None:
        self.app._clear_filters()

    def wait_for_issue_count(
        self,
        expected_count: int,
        *,
        timeout: float = 5.0,
        message: str | None = None,
    ) -> None:
        self._wait_until(
            lambda: self.issue_count() == expected_count,
            timeout=timeout,
            message=message or f"Results tab never reached {expected_count} issue cards",
        )


class BenchmarkTabHarness:
    """Test-facing helper for the benchmark browser tab."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def open(self) -> None:
        self.app.tabs.set(t("gui.tab.benchmarks"))
        self.app.update_idletasks()

    def current_tab(self) -> str:
        return str(self.app.tabs.get())

    def source_text(self) -> str:
        return str(self.app.benchmark_source_value.cget("text"))

    def count_text(self) -> str:
        return str(self.app.benchmark_count_value.cget("text"))

    def summary_selector_values(self) -> list[str]:
        menu = self.app.benchmark_summary_selector_menu
        try:
            values = menu.cget("values")
        except Exception:
            values = getattr(menu, "_values", ())
        return list(values)

    def selected_fixture(self) -> str:
        return str(self.app.benchmark_fixture_var.get())

    def selected_summary(self) -> str:
        return str(self.app.benchmark_summary_selector_var.get())

    def selected_fixture_filter(self) -> str:
        return str(self.app.benchmark_fixture_filter_var.get())

    def selected_fixture_sort(self) -> str:
        return str(self.app.benchmark_fixture_sort_var.get())

    def catalog_text(self) -> str:
        return self.app.benchmark_catalog_box.get("0.0", "end").strip()

    def detail_text(self) -> str:
        return self.app.benchmark_detail_box.get("0.0", "end").strip()

    def primary_summary_text(self) -> str:
        return self.app.benchmark_primary_summary_box.get("0.0", "end").strip()

    def compare_summary_text(self) -> str:
        return self.app.benchmark_compare_summary_box.get("0.0", "end").strip()

    def takeaways_text(self) -> str:
        return str(self.app.benchmark_takeaways_label.cget("text")).strip()

    def advanced_sources_visible(self) -> bool:
        return bool(self.app.benchmark_advanced_source_frame.winfo_manager())

    def toggle_advanced_sources(self) -> None:
        self.app.benchmark_advanced_toggle_btn.invoke()
        self.app.update_idletasks()

    def preview_primary_text(self) -> str:
        return self.app.benchmark_preview_primary_box.get("0.0", "end").strip()

    def preview_compare_text(self) -> str:
        return self.app.benchmark_preview_compare_box.get("0.0", "end").strip()

    def preview_diff_text(self) -> str:
        return self.app.benchmark_preview_diff_box.get("0.0", "end").strip()

    def fixture_diff_ids(self) -> list[str]:
        return list(getattr(self.app, "_benchmark_fixture_diff_rows", {}).keys())

    def fixture_diff_record(self, fixture_id: str) -> dict[str, Any]:
        rows = getattr(self.app, "_benchmark_fixture_diff_rows", {})
        if fixture_id not in rows:
            raise AssertionError(f"Fixture diff row {fixture_id!r} not found")
        return rows[fixture_id]

    def open_fixture_diff_primary_report(self, fixture_id: str) -> None:
        self.fixture_diff_record(fixture_id)["primary_button"].invoke()
        self.app.update_idletasks()

    def open_fixture_diff_compare_report(self, fixture_id: str) -> None:
        self.fixture_diff_record(fixture_id)["compare_button"].invoke()
        self.app.update_idletasks()

    def preview_fixture_diff_reports(self, fixture_id: str) -> None:
        self.fixture_diff_record(fixture_id)["preview_button"].invoke()
        self.app.update_idletasks()

    def diff_fixture_reports(self, fixture_id: str) -> None:
        self.fixture_diff_record(fixture_id)["diff_button"].invoke()
        self.app.update_idletasks()

    def load_catalog(self, fixtures_root: Path) -> None:
        self.app._load_benchmark_fixture_catalog(fixtures_root)
        self.app.update_idletasks()

    def load_summary(self, path: Path) -> None:
        self.app._load_benchmark_summary_artifact(path)
        self.app.update_idletasks()

    def compare_summary(self, path: Path) -> None:
        self.app._load_benchmark_summary_artifact(path, compare=True)
        self.app.update_idletasks()

    def refresh_summary_selector(self, artifacts_root: Path) -> None:
        self.app._refresh_benchmark_summary_selector(artifacts_root)
        self.app.update_idletasks()

    def select_summary(self, label: str) -> None:
        self.app.benchmark_summary_selector_var.set(label)

    def select_fixture_filter(self, label: str) -> None:
        self.app.benchmark_fixture_filter_var.set(label)
        self.app._on_fixture_diff_filter_selected(label)
        self.app.update_idletasks()

    def select_fixture_sort(self, label: str) -> None:
        self.app.benchmark_fixture_sort_var.set(label)
        self.app._on_fixture_diff_sort_selected(label)
        self.app.update_idletasks()

    def select_summary_by_fragment(self, fragment: str) -> str:
        for label in self.summary_selector_values():
            if fragment in label:
                self.select_summary(label)
                return label
        raise AssertionError(f"No benchmark summary selector entry contains {fragment!r}")

    def load_selected_summary(self) -> None:
        self.app._load_selected_benchmark_summary()
        self.app.update_idletasks()

    def compare_selected_summary(self) -> None:
        self.app._compare_selected_benchmark_summary()
        self.app.update_idletasks()

    def open_source_folder(self) -> None:
        self.app._open_benchmark_source_folder()
        self.app.update_idletasks()

    def open_summary_json(self) -> None:
        self.app._open_selected_benchmark_summary_json()
        self.app.update_idletasks()

    def open_report_directory(self) -> None:
        self.app._open_selected_benchmark_report_directory()
        self.app.update_idletasks()

    def filter_count_text(self) -> str:
        return str(self.app._filter_count_lbl.cget("text"))

    def set_severity_filter(self, value: str) -> None:
        self.app._filter_sev_var.set(value)

    def set_status_filter(self, value: str) -> None:
        self.app._filter_status_var.set(value)

    def set_type_filter(self, value: str) -> None:
        self.app._filter_type_var.set(value)

    def apply_filters(self) -> None:
        self.app._apply_filters()

    def clear_filters(self) -> None:
        self.app._clear_filters()

    def wait_for_issue_count(
        self,
        expected_count: int,
        *,
        timeout: float = 5.0,
        message: str | None = None,
    ) -> None:
        self._wait_until(
            lambda: self.issue_count() == expected_count,
            timeout=timeout,
            message=message or f"Results tab never reached {expected_count} issue cards",
        )


class GuiTestHarness:
    """Drive the GUI in tests using the same controls a user would touch."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.queue_panel = QueuePanelHarness(app)
        self.toasts: list[tuple[str, bool]] = []
        self._scheduled_callbacks: dict[str, tuple[float, Any, tuple[Any, ...]]] = {}
        self._after_counter = 0
        self._callback_lock = threading.Lock()

        def _capture_toast(
            message: str,
            *,
            duration: int = 6000,
            error: bool = False,
        ) -> None:
            self.toasts.append((message, error))

        def _after(delay_ms: int, callback: Any = None, *args: Any) -> str:
            with self._callback_lock:
                self._after_counter += 1
                token = f"gui-harness-after-{self._after_counter}"
            if callback is None:
                callback = lambda: None
            due = time.monotonic() + max(delay_ms, 0) / 1000.0
            with self._callback_lock:
                self._scheduled_callbacks[token] = (due, callback, args)
            return token

        def _after_cancel(token: str) -> None:
            with self._callback_lock:
                self._scheduled_callbacks.pop(token, None)

        self.app._show_toast = _capture_toast
        self.app.after = _after
        self.app.after_cancel = _after_cancel
        self.status_bar = StatusBarHarness(app, self.wait_until)
        self.review_runtime = ReviewRuntimeHarness(app)
        self.results_tab = ResultsTabHarness(app, self.wait_until)
        self.benchmark_tab = BenchmarkTabHarness(app)

    def pump(self, cycles: int = 1) -> None:
        for _ in range(cycles):
            self.app.update_idletasks()
            self.app.update()
            drain_ui_queue = getattr(self.app, "_drain_ui_call_queue", None)
            if callable(drain_ui_queue):
                drain_ui_queue()
            now = time.monotonic()
            with self._callback_lock:
                ready = [
                    token
                    for token, (due, _callback, _args) in self._scheduled_callbacks.items()
                    if due <= now
                ]
            for token in ready:
                with self._callback_lock:
                    scheduled = self._scheduled_callbacks.pop(token, None)
                if scheduled is None:
                    continue
                _due, callback, args = scheduled
                callback(*args)
            if callable(drain_ui_queue):
                drain_ui_queue()

    def wait_until(
        self,
        predicate: Any,
        *,
        timeout: float = 5.0,
        interval: float = 0.01,
        message: str | None = None,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if predicate():
                self.pump()
                return
            time.sleep(interval)
        raise AssertionError(message or "Condition not met before timeout")

    def enable_runtime_actions(self) -> None:
        self.app._testing_mode = False

    def set_entry(self, entry: Any, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def select_review_types(self, *review_types: str) -> None:
        selected = set(review_types)
        for key, var in self.app.type_vars.items():
            var.set(key in selected)

    def fill_valid_review_form(
        self,
        project_path: Path,
        *,
        review_types: tuple[str, ...] = ("security",),
        programmers: str = "Alice",
        reviewers: str = "Bob",
    ) -> None:
        self.app.scope_var.set("project")
        self.pump()
        self.set_entry(self.app.path_entry, str(project_path))
        self.set_entry(self.app.programmers_entry, programmers)
        self.set_entry(self.app.reviewers_entry, reviewers)
        self.app.file_select_mode_var.set("all")
        self.select_review_types(*review_types)
        self.pump()

    def start_review(self) -> None:
        self.app.run_btn.invoke()
        self.pump()

    def start_dry_run(self) -> None:
        self.app.dry_btn.invoke()
        self.pump()

    def start_health_check(self) -> None:
        self.app.health_btn.invoke()
        self.pump()

    def log_text(self) -> str:
        return self.app.log_box.get("0.0", "end").strip()

    def status_text(self) -> str:
        return self.status_bar.text()

    def wait_for_status(
        self,
        expected_text: str,
        *,
        timeout: float = 5.0,
        message: str | None = None,
    ) -> None:
        self.status_bar.wait_for_text(expected_text, timeout=timeout, message=message)
