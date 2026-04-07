from __future__ import annotations

from typing import Any

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