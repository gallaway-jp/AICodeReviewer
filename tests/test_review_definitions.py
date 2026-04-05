from __future__ import annotations

import json
from pathlib import Path

import pytest

from aicodereviewer.config import config
from aicodereviewer.review_definitions import compose_review_pack_state, compose_review_registry


def _write_pack(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compose_review_registry_loads_custom_subtype_pack(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path / "security-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "secure_defaults",
                    "parent_key": "security",
                    "label": "Secure Defaults",
                    "summary_key": "",
                    "aliases": ["secure-defaults"],
                    "prompt_append": "Also check for unsafe default configuration and opt-out security controls.",
                }
            ],
        },
    )

    registry = compose_review_registry([pack_path])

    definition = registry.get("secure_defaults")
    assert definition.parent_key == "security"
    assert definition.label == "Secure Defaults"
    assert definition.group == registry.get("security").group
    assert registry.resolve_key("secure-defaults") == "secure_defaults"
    assert registry.lineage_keys("secure_defaults") == ("secure_defaults", "security")
    assert definition.prompt.startswith(registry.get("security").prompt)
    assert "unsafe default configuration" in definition.prompt


def test_compose_review_registry_rejects_unknown_parent(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path / "bad-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "ghost_child",
                    "parent_key": "missing_parent",
                    "prompt": "Custom prompt",
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="unknown or cyclic parent definitions"):
        compose_review_registry([pack_path])


def test_compose_review_registry_empty_pack_list_uses_builtins_only() -> None:
    registry = compose_review_registry([])

    assert "security" in registry.visible_keys()
    assert "secure_defaults" not in registry.visible_keys()


def test_compose_review_pack_state_loads_custom_presets_and_extended_metadata(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path / "security-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "secure_defaults",
                    "parent_key": "security",
                    "label": "Secure Defaults",
                    "category_aliases": ["insecure_configuration", "unsafe_defaults"],
                    "context_augmentation_rules": ["Inspect bootstrap and first-run config paths."],
                    "benchmark_metadata": {"fixture_tags": ["security", "defaults"]},
                    "prompt_append": "Also check unsafe default configuration.",
                }
            ],
            "review_presets": [
                {
                    "key": "secure_runtime",
                    "aliases": ["secure-runtime"],
                    "label": "Secure Runtime",
                    "summary": "Security defaults plus input validation.",
                    "review_types": ["secure_defaults", "data_validation", "secure_defaults"],
                }
            ],
        },
    )

    registry, preset_definitions = compose_review_pack_state([pack_path])

    definition = registry.get("secure_defaults")
    assert definition.category_aliases == ("insecure_configuration", "unsafe_defaults")
    assert definition.context_augmentation_rules == ("Inspect bootstrap and first-run config paths.",)
    assert definition.benchmark_metadata == {"fixture_tags": ["security", "defaults"]}
    assert [preset.key for preset in preset_definitions][-1] == "secure_runtime"
    assert preset_definitions[-1].aliases == ("secure-runtime",)
    assert preset_definitions[-1].review_types == ("secure_defaults", "data_validation")


def test_compose_review_pack_state_rejects_unknown_preset_review_type(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path / "bad-preset-pack.json",
        {
            "version": 1,
            "review_presets": [
                {
                    "key": "bad_bundle",
                    "review_types": ["missing_type"],
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="unknown review type 'missing_type'"):
        compose_review_pack_state([pack_path])


def test_compose_review_registry_loads_review_pack_from_discovered_addon(monkeypatch, tmp_path: Path) -> None:
    addon_dir = tmp_path / "addons" / "secure_defaults"
    pack_path = _write_pack(
        addon_dir / "review-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "secure_defaults",
                    "parent_key": "security",
                    "label": "Secure Defaults",
                    "prompt_append": "Also check unsafe defaults.",
                }
            ],
        },
    )
    _write_pack(
        addon_dir / "addon.json",
        {
            "manifest_version": 1,
            "id": "secure-defaults-addon",
            "version": "1.0.0",
            "entry_points": {"review_packs": ["review-pack.json"]},
        },
    )

    original_config_path = config.config_path
    config.config_path = tmp_path / "config.ini"
    config.set_value("addons", "paths", "")
    config.set_value("review_packs", "paths", "")
    monkeypatch.setattr("aicodereviewer.addons._config_base_dir", lambda: tmp_path)
    monkeypatch.setattr("aicodereviewer.review_definitions._config_base_dir", lambda: tmp_path)

    try:
        registry = compose_review_registry()
    finally:
        config.config_path = original_config_path

    definition = registry.get("secure_defaults")
    assert definition.label == "Secure Defaults"
    assert definition.parent_key == "security"
    assert pack_path.exists()