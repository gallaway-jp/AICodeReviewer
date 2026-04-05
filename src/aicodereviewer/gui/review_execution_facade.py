"""Higher-level GUI review execution facade.

Owns the end-to-end review execution setup layered above the lower-level
review execution coordinator, including scan-function assembly and runner
construction for one review run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .review_execution_coordinator import ReviewExecutionCoordinator, ReviewExecutionOutcome


@dataclass
class ReviewExecutionFacade:
    """Coordinate one GUI review run above the execution coordinator."""

    coordinator: ReviewExecutionCoordinator

    def build_event_sink(
        self,
        publish_progress: Callable[[float, str], None],
    ) -> Any:
        """Return the GUI review event sink for one run."""
        return self.coordinator.build_event_sink(publish_progress)

    def build_scan_function(
        self,
        *,
        directory: Optional[str],
        selected_files: Optional[list[str]],
        diff_filter_file: Optional[str],
        diff_filter_commits: Optional[str],
        scan_project_with_scope_fn: Callable[..., list[Any]],
        get_diff_from_commits_fn: Callable[[str, str], Optional[str]],
        parse_diff_file_fn: Callable[[str], list[dict[str, Any]]],
    ) -> Callable[..., list[Any]]:
        """Build the scan function used by one review execution."""
        has_diff_filter = bool(diff_filter_file or diff_filter_commits)

        def _scan_fn(
            run_directory: Optional[str],
            scope: str,
            diff_file: Optional[str] = None,
            commits: Optional[str] = None,
        ) -> list[Any]:
            if scope == "diff":
                return scan_project_with_scope_fn(run_directory, scope, diff_file, commits)

            all_files: list[Any] = scan_project_with_scope_fn(run_directory, "project")
            if selected_files:
                selected_set = {Path(file_path).resolve() for file_path in selected_files}
                all_files = [file_path for file_path in all_files if Path(file_path).resolve() in selected_set]

            if not has_diff_filter:
                return all_files

            diff_content: Optional[str] = None
            if diff_filter_file:
                with open(diff_filter_file, "r", encoding="utf-8") as handle:
                    diff_content = handle.read()
            elif diff_filter_commits and directory:
                diff_content = get_diff_from_commits_fn(directory, diff_filter_commits)

            if not diff_content:
                return []

            diff_entries = parse_diff_file_fn(diff_content)
            diff_by_name = {entry["filename"]: entry["content"] for entry in diff_entries}
            intersected: list[Any] = []
            for file_path in all_files:
                resolved_path = Path(file_path)
                if run_directory:
                    try:
                        relative_path = str(resolved_path.relative_to(run_directory))
                    except ValueError:
                        relative_path = str(resolved_path)
                else:
                    relative_path = str(resolved_path)
                normalized_path = relative_path.replace("\\", "/")
                if normalized_path in diff_by_name:
                    intersected.append(
                        {
                            "path": resolved_path,
                            "content": diff_by_name[normalized_path],
                            "filename": normalized_path,
                        }
                    )
            return intersected

        return _scan_fn

    def execute_run(
        self,
        *,
        params: dict[str, Any],
        dry_run: bool,
        cancel_check: Callable[[], bool],
        publish_status: Callable[[str], None],
        create_client: Callable[[str], Any],
        create_runner: Callable[..., Any],
        event_sink: Any,
        scan_project_with_scope_fn: Callable[..., list[Any]],
        get_diff_from_commits_fn: Callable[[str, str], Optional[str]],
        parse_diff_file_fn: Callable[[str], list[dict[str, Any]]],
    ) -> ReviewExecutionOutcome:
        """Execute one review run and return its classified outcome."""
        run_params = dict(params)
        backend_name: str = run_params.pop("backend")
        selected_files: Optional[list[str]] = run_params.pop("selected_files", None)
        diff_filter_file: Optional[str] = run_params.pop("diff_filter_file", None)
        diff_filter_commits: Optional[str] = run_params.pop("diff_filter_commits", None)

        client = None
        if not dry_run:
            client = self.coordinator.activate_client(backend_name, create_client, publish_status)

        scan_fn = self.build_scan_function(
            directory=run_params.get("path"),
            selected_files=selected_files,
            diff_filter_file=diff_filter_file,
            diff_filter_commits=diff_filter_commits,
            scan_project_with_scope_fn=scan_project_with_scope_fn,
            get_diff_from_commits_fn=get_diff_from_commits_fn,
            parse_diff_file_fn=parse_diff_file_fn,
        )

        runner = create_runner(client, scan_fn=scan_fn, backend_name=backend_name)
        result = runner.run(
            **run_params,
            dry_run=dry_run,
            event_sink=event_sink,
            interactive=False,
            cancel_check=cancel_check,
        )

        return self.coordinator.classify_run_result(
            dry_run=dry_run,
            result=result,
            runner=runner,
            cancel_requested=cancel_check(),
        )