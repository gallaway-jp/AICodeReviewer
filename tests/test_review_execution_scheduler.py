from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicodereviewer.execution import ReviewExecutionResult, ReviewExecutionRuntime, ReviewRequest
from aicodereviewer.models import ReviewIssue
from aicodereviewer.gui.review_execution_coordinator import ReviewExecutionCoordinator, ReviewExecutionOutcome
from aicodereviewer.gui.review_execution_facade import ReviewExecutionFacade
from aicodereviewer.gui.review_execution_scheduler import ReviewExecutionScheduler
from aicodereviewer.gui.review_runtime import ActiveReviewController
from aicodereviewer.http_api import LocalReviewHttpService
from aicodereviewer.review_definitions import install_review_registry


def test_review_execution_scheduler_uses_runtime_jobs_visible_to_http() -> None:
    install_review_registry([])
    runtime = ReviewExecutionRuntime()
    scheduler = ReviewExecutionScheduler(
        ReviewExecutionFacade(ReviewExecutionCoordinator(ActiveReviewController())),
        runtime,
    )
    service = LocalReviewHttpService(runtime=runtime)
    release_event = threading.Event()

    def _execute(job, _cancel_event, _sink):
        job.transition_to("reviewing")
        if job.request.path == "./first":
            while not release_event.is_set():
                time.sleep(0.01)
        job.complete_with_result(
            ReviewExecutionResult(
                status="dry_run",
                request=job.request,
                files_scanned=1,
                target_paths=[job.request.path or ""],
            )
        )
        return ReviewExecutionOutcome(kind="dry_run_complete")

    first = scheduler.submit_run(
        request=ReviewRequest(
            path="./first",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            backend_name="local",
            dry_run=True,
        ),
        submission_kind="dry_run",
        execute_run=_execute,
        on_outcome=lambda _outcome: None,
        on_error=lambda exc: (_ for _ in ()).throw(exc),
        on_finished=lambda: None,
    )
    second = scheduler.submit_run(
        request=ReviewRequest(
            path="./second",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            backend_name="local",
            dry_run=True,
        ),
        submission_kind="dry_run",
        execute_run=_execute,
        on_outcome=lambda _outcome: None,
        on_error=lambda exc: (_ for _ in ()).throw(exc),
        on_finished=lambda: None,
    )

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        snapshots = scheduler.list_submission_snapshots()
        if len(snapshots) == 2:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Timed out waiting for scheduler snapshots")

    snapshots = scheduler.list_submission_snapshots()
    assert {snapshot.submission_id for snapshot in snapshots} == {first.submission_id, second.submission_id}
    assert any(snapshot.submission_id == first.submission_id and snapshot.is_active for snapshot in snapshots)
    assert any(snapshot.submission_id == second.submission_id and not snapshot.is_active for snapshot in snapshots)

    http_jobs = {item["job_id"]: item for item in service.list_jobs()}
    assert set(http_jobs) == {first.submission_id, second.submission_id}
    assert http_jobs[first.submission_id]["state"] == "reviewing"
    assert http_jobs[second.submission_id]["state"] == "queued"

    release_event.set()
    runtime.wait_for_job(first.submission_id, timeout=2.0)
    runtime.wait_for_job(second.submission_id, timeout=2.0)
    service.shutdown(wait=True, timeout=2.0)


def test_review_execution_scheduler_normalizes_no_report_outcomes_into_completed_runtime_jobs() -> None:
    install_review_registry([])
    runtime = ReviewExecutionRuntime()
    scheduler = ReviewExecutionScheduler(
        ReviewExecutionFacade(ReviewExecutionCoordinator(ActiveReviewController())),
        runtime,
    )

    submission = scheduler.submit_run(
        request=ReviewRequest(
            path="./project",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            backend_name="local",
        ),
        execute_run=lambda _job, _cancel_event, _sink: ReviewExecutionOutcome(kind="no_report"),
        on_outcome=lambda _outcome: None,
        on_error=lambda exc: (_ for _ in ()).throw(exc),
        on_finished=lambda: None,
    )

    job = runtime.wait_for_job(submission.submission_id, timeout=2.0)

    assert job.state == "completed"
    assert job.result is not None
    assert job.result.status == "no_issues"
    assert scheduler.get_submission_snapshot(submission.submission_id) is not None


def test_review_execution_scheduler_normalizes_issue_outcomes_into_pending_runtime_jobs() -> None:
    install_review_registry([])
    runtime = ReviewExecutionRuntime()
    scheduler = ReviewExecutionScheduler(
        ReviewExecutionFacade(ReviewExecutionCoordinator(ActiveReviewController())),
        runtime,
    )
    issue = ReviewIssue(file_path="./project/app.py", issue_type="security", description="x")
    runner = SimpleNamespace(
        serialized_report_context={
            "project_path": "./project",
            "review_types": ["security"],
            "scope": "project",
            "total_files_scanned": 1,
            "language": "en",
            "diff_source": None,
            "programmers": [],
            "reviewers": [],
            "backend": "local",
        }
    )

    submission = scheduler.submit_run(
        request=ReviewRequest(
            path="./project",
            scope="project",
            diff_file=None,
            commits=None,
            review_types=["security"],
            spec_content=None,
            target_lang="en",
            backend_name="local",
        ),
        execute_run=lambda _job, _cancel_event, _sink: ReviewExecutionOutcome(
            kind="issues_found",
            issues=[issue],
            runner=runner,
        ),
        on_outcome=lambda _outcome: None,
        on_error=lambda exc: (_ for _ in ()).throw(exc),
        on_finished=lambda: None,
    )

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        job = runtime.get_job(submission.submission_id)
        if job.state == "awaiting_gui_finalize":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Timed out waiting for pending GUI-finalize job state")

    job = runtime.get_job(submission.submission_id)
    assert job.result is not None
    assert job.result.status == "issues_found"
    assert job.result.issue_count == 1
    assert scheduler.get_submission_snapshot(submission.submission_id) is None