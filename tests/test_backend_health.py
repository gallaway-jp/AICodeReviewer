from __future__ import annotations

from typing import Any

import pytest

from aicodereviewer.backends import health


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "payload"

    def json(self) -> dict[str, Any]:
        return self._payload


def test_check_backend_resolves_local_provider_alias(monkeypatch):
    calls: list[str | None] = []

    def _fake_local(api_type_override: str | None = None):
        calls.append(api_type_override)
        return health.HealthReport(backend="local", ready=True, checks=[], summary="ok")

    monkeypatch.setattr(health, "check_local_llm", _fake_local)
    monkeypatch.setattr(health, "_run_connection_test", lambda _backend: health.CheckResult("conn", True))

    report = health.check_backend("ollama")

    assert report.backend == "local"
    assert calls == ["ollama"]


def test_check_backend_unknown_backend_returns_failed_report():
    report = health.check_backend("does-not-exist")

    assert report.ready is False
    assert report.backend == "does-not-exist"


def test_check_copilot_accepts_copilot_specific_token(monkeypatch):
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("copilot", "copilot_path"): "copilot",
        ("copilot", "model"): "auto",
    }.get((section, key), default))
    monkeypatch.setattr(health.shutil, "which", lambda _cmd: "C:/Tools/copilot.exe")
    monkeypatch.setattr(health, "_run_quiet", lambda *args, **kwargs: (0, "copilot 1.0.0", ""))
    monkeypatch.setattr(health.os.path, "isdir", lambda _path: False)
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "token")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(health, "_discover_copilot_models", lambda _path: ["gpt-5-mini"])

    report = health.check_copilot()

    assert report.ready is True
    auth_check = next(check for check in report.checks if check.name == health.t("health.copilot_auth"))
    assert auth_check.passed is True


def test_check_local_llm_uses_openai_models_endpoint_and_confirms_model(monkeypatch):
    requested_urls: list[str] = []

    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:1234/v1",
        ("local_llm", "api_type"): "openai",
        ("local_llm", "model"): "gpt-local",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))

    def _fake_get(url: str, timeout: int, headers: dict[str, str]):
        requested_urls.append(url)
        return _Response(200, {"data": [{"id": "gpt-local"}]})

    monkeypatch.setattr("requests.get", _fake_get)

    report = health.check_local_llm()

    assert requested_urls == ["http://localhost:1234/v1/models"]
    assert report.ready is True
    assert any(check.name == "Model Availability" and check.passed for check in report.checks)


def test_check_local_llm_reports_missing_configured_model(monkeypatch):
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:1234",
        ("local_llm", "api_type"): "lmstudio",
        ("local_llm", "model"): "missing-model",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))
    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout, headers: _Response(200, {"data": [{"id": "loaded-model"}]}),
    )

    report = health.check_local_llm()

    assert report.ready is False
    model_check = next(check for check in report.checks if check.name == "Model Availability")
    assert model_check.passed is False


def test_check_local_llm_uses_ollama_tags_endpoint(monkeypatch):
    requested_urls: list[str] = []
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:11434/api",
        ("local_llm", "api_type"): "ollama",
        ("local_llm", "model"): "llama3",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))

    def _fake_get(url: str, timeout: int, headers: dict[str, str]):
        requested_urls.append(url)
        return _Response(200, {"models": [{"name": "llama3"}]})

    monkeypatch.setattr("requests.get", _fake_get)

    report = health.check_local_llm()

    assert requested_urls == ["http://localhost:11434/api/tags"]
    assert report.ready is True


def test_check_local_llm_uses_lmstudio_models_endpoint_after_normalization(monkeypatch):
    requested_urls: list[str] = []
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:1234/v1/",
        ("local_llm", "api_type"): "lmstudio",
        ("local_llm", "model"): "auto",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))

    def _fake_get(url: str, timeout: int, headers: dict[str, str]):
        requested_urls.append(url)
        return _Response(200, {"data": [{"id": "model-a"}]})

    monkeypatch.setattr("requests.get", _fake_get)

    report = health.check_local_llm()

    assert requested_urls == ["http://localhost:1234/api/v1/models"]
    assert report.ready is True


def test_check_local_llm_anthropic_requires_explicit_model(monkeypatch):
    requested_urls: list[str] = []
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:8000/v1",
        ("local_llm", "api_type"): "anthropic",
        ("local_llm", "model"): "default",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))

    def _fake_get(url: str, timeout: int, headers: dict[str, str]):
        requested_urls.append(url)
        return _Response(405, {})

    monkeypatch.setattr("requests.get", _fake_get)

    report = health.check_local_llm()

    assert requested_urls == ["http://localhost:8000/v1/messages"]
    assert report.ready is False
    model_check = next(check for check in report.checks if check.name == "Model Availability")
    assert model_check.passed is False


def test_check_local_llm_rejects_unknown_api_type(monkeypatch):
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: {
        ("local_llm", "api_url"): "http://localhost:1234",
        ("local_llm", "api_type"): "mystery",
        ("local_llm", "model"): "default",
        ("local_llm", "api_key"): "",
    }.get((section, key), default))

    report = health.check_local_llm()

    assert report.ready is False
    api_type_check = next(check for check in report.checks if check.name == "API Type")
    assert api_type_check.passed is False


def test_check_bedrock_reports_missing_aws_cli(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(health.config, "get", lambda section, key, default=None: default)

    report = health.check_bedrock()

    assert report.ready is False
    assert report.checks[0].passed is False


def test_check_kiro_reports_missing_wsl(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _cmd: None)

    report = health.check_kiro()

    assert report.ready is False
    assert report.checks[0].name == "WSL"
    assert report.checks[0].passed is False