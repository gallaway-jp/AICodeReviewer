from __future__ import annotations

from pathlib import Path

import pytest

from aicodereviewer.benchmarking import discover_fixtures
from tools import run_review_type_degradation_study as study


FIXTURES_ROOT = Path("benchmarks/holistic_review/fixtures")


def test_parse_levels_includes_baseline_and_clamps():
    assert study._parse_levels("4,1,100", 22) == [1, 4, 22]


def test_type_set_for_level_keeps_target_first():
    selected = study._type_set_for_level("security", 4, ["accessibility", "security", "testing", "ui_ux", "regression"])

    assert selected == ["security", "accessibility", "testing", "ui_ux"]


def test_valid_review_types_for_fixture_skips_spec_without_spec_file():
    fixture = type("Fixture", (), {"spec_file": None})()

    valid = study._valid_review_types_for_fixture(
        fixture,
        ["accessibility", "specification", "security"],
    )

    assert valid == ["accessibility", "security"]


def test_type_set_for_fixture_level_omits_invalid_specification_distractor():
    fixture = type("Fixture", (), {"id": "demo", "review_types": ["security"], "spec_file": None})()

    selected = study._type_set_for_fixture_level(
        fixture,
        3,
        ["accessibility", "security", "specification", "testing"],
    )

    assert selected == ["security", "accessibility", "testing"]


def test_select_fixtures_uses_curated_representatives():
    fixtures = discover_fixtures(FIXTURES_ROOT)
    args = type("Args", (), {"fixtures": [], "review_types": ["best_practices", "specification"]})()

    selected = study._select_fixtures(args, fixtures)

    assert [fixture.id for fixture in selected] == [
        "private-state-access-bypass",
        "specification-type-mismatch-vs-spec-enum",
    ]


def test_select_fixtures_rejects_unknown_review_type():
    fixtures = discover_fixtures(FIXTURES_ROOT)
    args = type("Args", (), {"fixtures": [], "review_types": ["unknown_type"]})()

    with pytest.raises(ValueError, match="Unknown review types"):
        study._select_fixtures(args, fixtures)


def test_build_summary_payload_includes_representative_fixture_metadata():
    fixture = type(
        "Fixture",
        (),
        {
            "id": "fixture-1",
            "title": "Fixture 1",
            "scope": "project",
            "review_types": ["security"],
        },
    )()
    args = type("Args", (), {"backend": None})()

    payload = study._build_summary_payload(
        args,
        [fixture],
        [1, 2],
        [],
        0,
        status="completed",
    )

    assert payload["representative_fixture_ids"] == ["fixture-1"]
    assert payload["representative_fixtures"][0]["id"] == "fixture-1"
    assert payload["representative_fixtures"][0]["review_types"] == ["security"]