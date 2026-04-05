from __future__ import annotations

from aicodereviewer.execution import ReviewExecutionRuntime, ReviewExecutionService, ReviewRequest
from aicodereviewer.models import ReviewIssue


def test_runtime_records_events_for_completed_dry_run_job() -> None:
    runtime = ReviewExecutionRuntime(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
        dry_run=True,
    )

    job = runtime.submit_job(request)
    runtime.wait_for_job(job.job_id, timeout=2.0)
    events = runtime.read_events(job_id=job.job_id, after_sequence=0, timeout=0.0)

    assert events
    assert events[0].event.kind == "job.state_changed"
    assert any(event.event.kind == "job.result_available" for event in events)
    runtime.shutdown(wait=True, timeout=2.0)


def test_runtime_lists_report_artifacts_for_completed_job(tmp_path) -> None:
    runtime = ReviewExecutionRuntime(
        execution_service=ReviewExecutionService(
            scan_fn=lambda *_args: [{"path": "src/example.py"}],
            collect_issues_fn=lambda *_args, **_kwargs: [
                ReviewIssue(
                    file_path="src/example.py",
                    issue_type="security",
                    severity="high",
                    description="Unsafe subprocess usage",
                    code_snippet="subprocess.run(cmd, shell=True)",
                    ai_feedback="Avoid shell=True for untrusted input.",
                )
            ],
        ),
        backend_factory=lambda _backend_name: object(),
    )
    request = ReviewRequest(
        path="./proj",
        scope="project",
        diff_file=None,
        commits=None,
        review_types=["security"],
        spec_content=None,
        target_lang="en",
        backend_name="local",
        dry_run=False,
    )

    job = runtime.submit_job(request, output_file=str(tmp_path / "report.json"))
    runtime.wait_for_job(job.job_id, timeout=2.0)
    artifacts = runtime.list_job_artifacts(job.job_id)

    keys = {artifact.key for artifact in artifacts}
    assert "report_primary" in keys
    assert len(artifacts) >= 1
    runtime.shutdown(wait=True, timeout=2.0)