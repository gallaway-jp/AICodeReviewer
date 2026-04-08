"""Validate generated addon heuristics against a curated external repository catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from aicodereviewer.addon_validation import (
    ensure_repository_checkout,
    evaluate_external_repository,
    load_external_repository_catalog,
    summarize_external_repository_results,
)


def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "addon_generation" / "external_repo_catalog.json"


def _default_repos_root() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "external-repo-samples"


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "generated-addon-validation"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generated addon heuristics and relevance against curated external repositories.",
    )
    parser.add_argument("--catalog", default=str(_default_catalog_path()))
    parser.add_argument("--repos-root", default=str(_default_repos_root()))
    parser.add_argument("--output-dir", default=str(_default_output_dir()))
    parser.add_argument("--repo-id", action="append", dest="repo_ids", default=[])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-clone", action="store_true")
    parser.add_argument("--json-out")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = load_external_repository_catalog(args.catalog)
    if args.repo_ids:
        selected = set(args.repo_ids)
        targets = [target for target in targets if target.repo_id in selected]
        missing = selected.difference({target.repo_id for target in targets})
        if missing:
            parser.error(f"Unknown repo ids: {', '.join(sorted(missing))}")

    results = []
    failures = []
    for target in targets:
        try:
            checkout_path = ensure_repository_checkout(
                target,
                args.repos_root,
                refresh=args.refresh,
                skip_clone=args.skip_clone,
            )
            results.append(evaluate_external_repository(target, checkout_path, args.output_dir))
        except Exception as exc:
            failures.append({
                "repo_id": target.repo_id,
                "repo_url": target.repo_url,
                "error": str(exc),
            })

    summary = summarize_external_repository_results(results)
    if failures:
        summary["status"] = "partial_failure"
        summary["failures"] = failures
    else:
        summary["status"] = "completed"

    rendered = json.dumps(summary, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())