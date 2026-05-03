from __future__ import annotations

from typing import Any
from types import SimpleNamespace

import aicodereviewer.gui.health_mixin as health_mixin
from aicodereviewer.gui.health_mixin import HealthMixin


class _DummyController:
    def __init__(self, *, allow_begin: bool = True) -> None:
        self.allow_begin = allow_begin
        self.begin_calls: list[str] = []
        self.finish_calls: list[str] = []

    def begin(self, backend_name: str) -> bool:
        self.begin_calls.append(backend_name)
        return self.allow_begin

    def finish(self, backend_name: str) -> None:
        self.finish_calls.append(backend_name)


class _DummyCombo:
    def __init__(self, current: str) -> None:
        self.current = current
        self.configured_values: list[str] | None = None
        self.set_calls: list[str] = []

    def get(self) -> str:
        return self.current

    def configure(self, *, values: list[str]) -> None:
        self.configured_values = values

    def set(self, value: str) -> None:
        self.current = value
        self.set_calls.append(value)


class _ImmediateThread:
    def __init__(self, *, target: Any, daemon: bool) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


class _Harness(HealthMixin):
    def __init__(self, controller: _DummyController, combo: _DummyCombo) -> None:
        self._active_model_refresh = controller
        self._kiro_model_combo = combo

    def after(self, _delay: int, callback: Any) -> None:
        callback()


def test_apply_kiro_models_preserves_current_selection_when_it_still_exists() -> None:
    combo = _DummyCombo("claude-sonnet-4")
    harness = _Harness(_DummyController(), combo)

    harness._apply_kiro_models(["claude-sonnet-4", "claude-opus-4"])

    assert combo.configured_values == ["claude-sonnet-4", "claude-opus-4"]
    assert combo.set_calls == ["claude-sonnet-4"]


def test_apply_kiro_models_does_not_force_missing_selection() -> None:
    combo = _DummyCombo("custom-model")
    harness = _Harness(_DummyController(), combo)

    harness._apply_kiro_models(["claude-sonnet-4", "claude-opus-4"])

    assert combo.configured_values == ["claude-sonnet-4", "claude-opus-4"]
    assert combo.set_calls == []


def test_refresh_kiro_model_list_async_uses_configured_cli_and_distro(monkeypatch: Any) -> None:
    controller = _DummyController()
    combo = _DummyCombo("claude-sonnet-4")
    harness = _Harness(controller, combo)
    observed_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        health_mixin.config,
        "get",
        lambda section, key, default=None: {
            ("kiro", "cli_command"): "kiro-cli",
            ("kiro", "wsl_distro"): "Ubuntu-24.04",
        }.get((section, key), default),
    )
    monkeypatch.setattr(
        health_mixin,
        "get_kiro_models",
        lambda kiro_path, wsl_distro: observed_calls.append((kiro_path, wsl_distro))
        or ["claude-sonnet-4", "claude-opus-4"],
    )
    monkeypatch.setattr(health_mixin.threading, "Thread", _ImmediateThread)

    harness._refresh_kiro_model_list_async()

    assert controller.begin_calls == ["kiro"]
    assert controller.finish_calls == ["kiro"]
    assert observed_calls == [("kiro-cli", "Ubuntu-24.04")]
    assert combo.configured_values == ["claude-sonnet-4", "claude-opus-4"]
    assert combo.set_calls == ["claude-sonnet-4"]


def test_refresh_kiro_model_list_async_skips_work_when_refresh_is_already_active(monkeypatch: Any) -> None:
    controller = _DummyController(allow_begin=False)
    combo = _DummyCombo("claude-sonnet-4")
    harness = _Harness(controller, combo)

    monkeypatch.setattr(
        health_mixin,
        "get_kiro_models",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fetch models")),
    )

    harness._refresh_kiro_model_list_async()

    assert controller.begin_calls == ["kiro"]
    assert controller.finish_calls == []
    assert combo.configured_values is None
    assert combo.set_calls == []


def test_split_fix_hint_url_extracts_before_url_and_after() -> None:
    parts = HealthMixin._split_fix_hint_url(
        "Install the AWS CLI from https://aws.amazon.com/cli/ and run 'aws configure sso'."
    )

    assert parts == (
        "Install the AWS CLI from",
        "https://aws.amazon.com/cli/",
        "and run 'aws configure sso'.",
    )


def test_render_health_fix_hint_with_url_renders_text_and_clickable_doc_link(monkeypatch: Any) -> None:
    created: list[Any] = []
    opened: list[str] = []

    class _DummyLabel:
        def __init__(self, _parent: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.grid_kwargs: dict[str, Any] | None = None
            self.bindings: list[tuple[str, Any]] = []
            created.append(self)

        def grid(self, **kwargs: Any) -> None:
            self.grid_kwargs = kwargs

        def bind(self, event: str, callback: Any) -> None:
            self.bindings.append((event, callback))

    monkeypatch.setattr(health_mixin.ctk, "CTkLabel", _DummyLabel)
    monkeypatch.setattr(health_mixin.ctk, "CTkFont", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(health_mixin.webbrowser, "open", lambda url: opened.append(url))

    harness = _Harness(_DummyController(), _DummyCombo("claude-sonnet-4"))
    hint = "Install the AWS CLI from https://aws.amazon.com/cli/ and run 'aws configure sso'."

    harness._render_health_fix_hint(object(), 7, hint)

    assert len(created) == 2
    assert created[0].kwargs["text"] == f"💡 {hint}"
    assert created[0].grid_kwargs == {"row": 7, "column": 1, "sticky": "w", "padx": 4, "pady": (0, 2)}
    assert created[1].kwargs["text"] == f"{health_mixin.t('health.link_label')} https://aws.amazon.com/cli/"
    assert created[1].grid_kwargs == {"row": 8, "column": 1, "sticky": "w", "padx": 18, "pady": (0, 4)}
    assert created[1].bindings and created[1].bindings[0][0] == "<Button-1>"

    created[1].bindings[0][1](None)

    assert opened == ["https://aws.amazon.com/cli/"]