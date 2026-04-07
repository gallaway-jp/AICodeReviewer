from __future__ import annotations

import json
from pathlib import Path

from aicodereviewer.benchmarking import discover_fixtures
from aicodereviewer.gui.benchmark_mixin import BenchmarkTabMixin


class _DummyEntry:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class _DummyBenchmarkApp(BenchmarkTabMixin):
    def __init__(self, artifacts_root: Path) -> None:
        self.benchmark_artifacts_root_entry = _DummyEntry(str(artifacts_root))


def test_validate_benchmark_summary_path_rejects_path_outside_artifacts_root(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    summary_path = tmp_path / "outside-summary.json"
    summary_path.write_text("{}", encoding="utf-8")
    app = _DummyBenchmarkApp(artifacts_root)

    try:
        app._validate_benchmark_summary_path(summary_path)
    except ValueError as exc:
        assert "configured saved runs folder" in str(exc)
    else:
        raise AssertionError("Expected summary path outside artifacts root to be rejected")


def test_resolve_artifact_path_rejects_summary_report_escape(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    artifacts_root.mkdir()
    reports_dir = artifacts_root / "reports"
    reports_dir.mkdir()
    summary_path = artifacts_root / "summary.json"
    summary_path.write_text(json.dumps({"generated_reports": []}), encoding="utf-8")
    app = _DummyBenchmarkApp(artifacts_root)

    resolved = app._resolve_artifact_path("reports/result.json", summary_path.parent)
    assert resolved == (reports_dir / "result.json").resolve()

    try:
        app._resolve_artifact_path(str(tmp_path / "escape" / "result.json"), summary_path.parent)
    except ValueError as exc:
        assert "escapes the allowed saved runs root" in str(exc)
    else:
        raise AssertionError("Expected external report path to be rejected")


def test_discover_fixtures_rejects_manifest_path_escape(tmp_path: Path) -> None:
    fixtures_root = tmp_path / "fixtures"
    scenario_dir = fixtures_root / "scenario-a"
    scenario_dir.mkdir(parents=True)
    external_root = tmp_path / "external"
    external_root.mkdir()
    (scenario_dir / "fixture.json").write_text(
        json.dumps(
            {
                "id": "scenario-a",
                "title": "Scenario A",
                "description": "Fixture manifest should not escape the configured fixtures root.",
                "scope": "project",
                "review_types": ["security"],
                "project_dir": str(external_root),
                "expected_findings": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        discover_fixtures(fixtures_root)
    except ValueError as exc:
        assert "must stay within the fixtures root" in str(exc)
    else:
        raise AssertionError("Expected fixture manifest path escape to be rejected")