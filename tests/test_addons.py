from __future__ import annotations

import json
from pathlib import Path

import pytest

from aicodereviewer.addons import (
    AddonEditorDiagnostic,
    AddonUIContributorSpec,
    collect_addon_editor_diagnostics,
    compose_addon_runtime,
    emit_addon_editor_event,
    emit_addon_editor_buffer_event,
    emit_addon_patch_applied_event,
    discover_addon_review_pack_paths,
    get_active_addon_runtime,
    install_addon_runtime,
    load_addon_manifest,
    load_addon_manifests,
)
from aicodereviewer.backends import create_backend, get_backend_choices


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_addon_manifest_resolves_review_pack_entry_points(tmp_path: Path) -> None:
    review_pack_path = _write_json(
        tmp_path / "secure_defaults" / "review-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "secure_defaults",
                    "parent_key": "security",
                    "prompt_append": "Check unsafe defaults.",
                }
            ],
        },
    )
    manifest_path = _write_json(
        tmp_path / "secure_defaults" / "addon.json",
        {
            "manifest_version": 1,
            "id": "secure-defaults-addon",
            "version": "1.0.0",
            "name": "Secure Defaults Addon",
            "compatibility": {"min_app_version": "2.0.0"},
            "permissions": ["review_definitions"],
            "entry_points": {
                "review_packs": ["review-pack.json"],
                "ui_contributors": [
                    {
                        "surface": "settings_section",
                        "title": "Secure Defaults",
                        "description": "Documents the review pack contribution.",
                        "lines": ["Review pack: secure_defaults"],
                    }
                ],
            },
        },
    )

    manifest = load_addon_manifest(manifest_path)

    assert manifest.addon_id == "secure-defaults-addon"
    assert manifest.addon_version == "1.0.0"
    assert manifest.permissions == ("review_definitions",)
    assert manifest.review_pack_paths == (review_pack_path.resolve(),)
    assert manifest.entry_points["review_packs"] == (str(review_pack_path.resolve()),)
    assert manifest.ui_contributor_specs == (
        AddonUIContributorSpec(
            addon_id="secure-defaults-addon",
            surface="settings_section",
            title="Secure Defaults",
            description="Documents the review pack contribution.",
            lines=("Review pack: secure_defaults",),
        ),
    )


def test_load_addon_manifest_rejects_incompatible_version(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "future_addon" / "addon.json",
        {
            "manifest_version": 1,
            "id": "future-addon",
            "version": "1.0.0",
            "compatibility": {"min_app_version": "99.0.0"},
        },
    )

    with pytest.raises(ValueError, match="requires AICodeReviewer >= 99.0.0"):
        load_addon_manifest(manifest_path)


def test_load_addon_manifest_rejects_review_pack_escape_from_addon_root(tmp_path: Path) -> None:
    shared_pack = _write_json(
        tmp_path / "shared" / "review-pack.json",
        {
            "version": 1,
            "review_definitions": [{"key": "shared", "parent_key": "security"}],
        },
    )
    manifest_path = _write_json(
        tmp_path / "addon" / "addon.json",
        {
            "manifest_version": 1,
            "id": "escape-addon",
            "version": "1.0.0",
            "entry_points": {"review_packs": [str(shared_pack)]},
        },
    )

    with pytest.raises(ValueError, match="must stay within the addon root"):
        load_addon_manifest(manifest_path)


def test_load_addon_manifests_rejects_duplicate_ids(tmp_path: Path) -> None:
    manifest_a = _write_json(
        tmp_path / "addon_a" / "addon.json",
        {
            "manifest_version": 1,
            "id": "duplicate-addon",
            "version": "1.0.0",
        },
    )
    manifest_b = _write_json(
        tmp_path / "addon_b" / "addon.json",
        {
            "manifest_version": 1,
            "id": "duplicate-addon",
            "version": "1.0.1",
        },
    )

    with pytest.raises(ValueError, match="Duplicate addon id 'duplicate-addon'"):
        load_addon_manifests([manifest_a, manifest_b])


def test_discover_addon_review_pack_paths_uses_default_addon_directory(monkeypatch, tmp_path: Path) -> None:
    review_pack_path = _write_json(
        tmp_path / "addons" / "secure_defaults" / "review-pack.json",
        {
            "version": 1,
            "review_definitions": [
                {
                    "key": "secure_defaults",
                    "parent_key": "security",
                    "prompt_append": "Check unsafe defaults.",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "addons" / "secure_defaults" / "addon.json",
        {
            "manifest_version": 1,
            "id": "secure-defaults-addon",
            "version": "1.0.0",
            "entry_points": {"review_packs": ["review-pack.json"]},
        },
    )

    monkeypatch.setattr("aicodereviewer.addons._config_base_dir", lambda: tmp_path)

    assert discover_addon_review_pack_paths() == [review_pack_path.resolve()]


def test_compose_addon_runtime_collects_backend_provider_diagnostics(tmp_path: Path) -> None:
    provider_module = tmp_path / "addons" / "broken_provider" / "backend_provider.py"
    provider_module.parent.mkdir(parents=True, exist_ok=True)
    provider_module.write_text(
        "def build_backend(**kwargs):\n"
        "    return object()\n",
        encoding="utf-8",
    )
    manifest_path = _write_json(
        provider_module.parent / "addon.json",
        {
            "manifest_version": 1,
            "id": "broken-provider-addon",
            "version": "1.0.0",
            "name": "Broken Provider Addon",
            "entry_points": {
                "backend_providers": [
                    {
                        "key": "broken-provider",
                        "display_name": "Broken Provider",
                        "module": "backend_provider.py",
                        "factory": "build_backend",
                    }
                ]
            },
        },
    )

    runtime = compose_addon_runtime([manifest_path])

    assert [manifest.addon_id for manifest in runtime.manifests] == ["broken-provider-addon"]
    assert runtime.backend_descriptors == ()
    assert len(runtime.diagnostics) == 1
    assert "failed to register backend provider 'broken-provider'" in runtime.diagnostics[0].message


def test_load_addon_manifest_resolves_editor_hook_entry_points(tmp_path: Path) -> None:
    hook_module = tmp_path / "addons" / "editor_hooks" / "editor_hooks.py"
    hook_module.parent.mkdir(parents=True, exist_ok=True)
    hook_module.write_text(
        "class DemoEditorHooks:\n"
        "    def on_buffer_event(self, payload):\n"
        "        return None\n"
        "\n"
        "def build_editor_hooks():\n"
        "    return DemoEditorHooks()\n",
        encoding="utf-8",
    )
    manifest_path = _write_json(
        hook_module.parent / "addon.json",
        {
            "manifest_version": 1,
            "id": "editor-hook-addon",
            "version": "1.0.0",
            "entry_points": {
                "editor_hooks": [
                    {
                        "module": "editor_hooks.py",
                        "factory": "build_editor_hooks",
                    }
                ]
            },
        },
    )

    manifest = load_addon_manifest(manifest_path)

    assert len(manifest.editor_hook_specs) == 1
    assert manifest.editor_hook_specs[0].factory_name == "build_editor_hooks"
    assert manifest.entry_points["editor_hooks"] == ("build_editor_hooks",)


def test_install_addon_runtime_registers_editor_hooks_and_dispatches_events(monkeypatch, tmp_path: Path) -> None:
    hook_module = tmp_path / "addons" / "editor_hooks" / "editor_hooks.py"
    hook_module.parent.mkdir(parents=True, exist_ok=True)
    hook_module.write_text(
        "class DemoEditorHooks:\n"
        "    def __init__(self):\n"
        "        self.buffer_events = []\n"
        "        self.editor_events = []\n"
        "        self.patch_events = []\n"
        "\n"
        "    def on_buffer_event(self, payload):\n"
        "        self.buffer_events.append((payload['event'], payload['buffer_key']))\n"
        "\n"
        "    def on_editor_event(self, payload):\n"
        "        self.editor_events.append(payload['event'])\n"
        "\n"
        "    def collect_diagnostics(self, payload):\n"
        "        if 'TODO' in payload.get('content', ''):\n"
        "            return [{'message': 'TODO marker present', 'severity': 'warning'}]\n"
        "        return []\n"
        "\n"
        "    def on_patch_applied(self, payload):\n"
        "        self.patch_events.append((payload['source'], payload['file_path']))\n"
        "\n"
        "def build_editor_hooks():\n"
        "    return DemoEditorHooks()\n",
        encoding="utf-8",
    )
    manifest_path = _write_json(
        hook_module.parent / "addon.json",
        {
            "manifest_version": 1,
            "id": "editor-hook-addon",
            "version": "1.0.0",
            "entry_points": {
                "editor_hooks": [
                    {
                        "module": "editor_hooks.py",
                        "factory": "build_editor_hooks",
                    }
                ]
            },
        },
    )

    monkeypatch.setattr("aicodereviewer.addons._config_base_dir", lambda: tmp_path)

    original_runtime = get_active_addon_runtime()
    try:
        runtime = install_addon_runtime([manifest_path])

        assert len(runtime.editor_hooks) == 1
        handler = runtime.editor_hooks[0].handler

        emit_addon_editor_buffer_event(
            "buffer_opened",
            {"buffer_key": "working", "content": "TODO: follow up"},
            runtime=runtime,
        )
        diagnostics = collect_addon_editor_diagnostics(
            {"buffer_key": "working", "content": "TODO: follow up"},
            runtime=runtime,
        )
        emit_addon_editor_event(
            "staged_preview_opened",
            {"surface": "diff_preview", "file_path": "src/demo.py"},
            runtime=runtime,
        )
        emit_addon_patch_applied_event(
            {"source": "editor_save", "file_path": "src/demo.py"},
            runtime=runtime,
        )

        assert handler.buffer_events == [("buffer_opened", "working")]
        assert diagnostics == (
            AddonEditorDiagnostic(
                addon_id="editor-hook-addon",
                message="TODO marker present",
                severity="warning",
            ),
        )
        assert handler.editor_events == ["buffer_opened", "staged_preview_opened"]
        assert handler.patch_events == [("editor_save", "src/demo.py")]
    finally:
        install_addon_runtime([manifest.manifest_path for manifest in original_runtime.manifests])


def test_example_editor_hook_addon_manifest_registers_real_hooks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "examples" / "addon-editor-hooks" / "addon.json"

    original_runtime = get_active_addon_runtime()
    try:
        runtime = install_addon_runtime([manifest_path])

        assert [manifest.addon_id for manifest in runtime.manifests] == ["editor-hook-addon"]
        assert len(runtime.editor_hooks) == 1
        diagnostics = collect_addon_editor_diagnostics(
            {
                "surface": "diff_preview",
                "current_content": "safe_run(user_input)\n",
                "change_count": 1,
                "content": "TODO: follow up",
            },
            runtime=runtime,
        )
        assert any(diagnostic.message for diagnostic in diagnostics)
    finally:
        install_addon_runtime([manifest.manifest_path for manifest in original_runtime.manifests])


def test_install_addon_runtime_registers_backend_provider(monkeypatch, tmp_path: Path) -> None:
    provider_module = tmp_path / "addons" / "echo_provider" / "backend_provider.py"
    provider_module.parent.mkdir(parents=True, exist_ok=True)
    provider_module.write_text(
        "from aicodereviewer.backends.base import AIBackend\n\n"
        "class EchoBackend(AIBackend):\n"
        "    def get_review(self, code_content, review_type='best_practices', lang='en', spec_content=None):\n"
        "        return 'ok'\n\n"
        "    def get_fix(self, code_content, issue_feedback, review_type='best_practices', lang='en'):\n"
        "        return code_content\n\n"
        "    def validate_connection(self):\n"
        "        return True\n\n"
        "def build_backend(**kwargs):\n"
        "    return EchoBackend()\n",
        encoding="utf-8",
    )
    manifest_path = _write_json(
        provider_module.parent / "addon.json",
        {
            "manifest_version": 1,
            "id": "echo-provider-addon",
            "version": "1.0.0",
            "name": "Echo Provider Addon",
            "entry_points": {
                "backend_providers": [
                    {
                        "key": "echo-provider",
                        "display_name": "Echo Provider",
                        "module": "backend_provider.py",
                        "factory": "build_backend",
                        "aliases": ["echo-provider-alias"],
                    }
                ]
            },
        },
    )

    monkeypatch.setattr("aicodereviewer.addons._config_base_dir", lambda: tmp_path)

    original_runtime = get_active_addon_runtime()
    try:
        runtime = install_addon_runtime([manifest_path])

        assert [manifest.addon_id for manifest in runtime.manifests] == ["echo-provider-addon"]
        assert [descriptor.key for descriptor in runtime.backend_descriptors] == ["echo-provider"]
        assert "echo-provider" in get_backend_choices()
        assert "echo-provider-alias" in get_backend_choices()
        assert create_backend("echo-provider").validate_connection() is True
        assert create_backend("echo-provider-alias").validate_connection() is True
    finally:
        install_addon_runtime([manifest.manifest_path for manifest in original_runtime.manifests])


def test_example_backend_addon_manifest_registers_real_backend_provider() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "examples" / "addon-echo-backend" / "addon.json"

    original_runtime = get_active_addon_runtime()
    try:
        runtime = install_addon_runtime([manifest_path])

        assert [manifest.addon_id for manifest in runtime.manifests] == ["echo-backend-addon"]
        assert [descriptor.key for descriptor in runtime.backend_descriptors] == ["echo-addon"]
        assert len(runtime.manifests[0].ui_contributor_specs) == 1
        assert runtime.manifests[0].ui_contributor_specs[0].title == "Echo Backend Addon"
        assert "echo-addon" in get_backend_choices()
        assert "echo-addon-example" in get_backend_choices()

        backend = create_backend("echo-addon")
        assert backend.validate_connection() is True
        assert "EchoAddonBackend review stub" in backend.get_review("print('hello')", review_type="security")
    finally:
        install_addon_runtime([manifest.manifest_path for manifest in original_runtime.manifests])