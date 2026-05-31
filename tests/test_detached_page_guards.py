from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from aicodereviewer.gui.addon_review_mixin import AddonReviewTabMixin
from aicodereviewer.gui.benchmark_mixin import BenchmarkTabMixin
from aicodereviewer.i18n import t


class _DummyWindow:
    def __init__(self, *, exists: bool) -> None:
        self._exists = exists

    def winfo_exists(self) -> bool:
        return self._exists


class _DummySurfaces:
    def __init__(self, *, detached: bool) -> None:
        self.detached = detached

    def is_page_detached(self, _page_key: str) -> bool:
        return self.detached


class _BenchmarkHarness(BenchmarkTabMixin):
    def __init__(self, *, window: Any, detached: bool) -> None:
        self._detached_benchmark_window = window
        self._surfaces = _DummySurfaces(detached=detached)

    def _app_helpers(self) -> Any:
        return SimpleNamespace(surfaces=lambda: self._surfaces)


class _Tabs:
    def __init__(self) -> None:
        self.selected: list[str] = []

    def set(self, value: str) -> None:
        self.selected.append(value)


class _AddonReviewHarness(AddonReviewTabMixin):
    def __init__(self, *, window: Any, detached: bool) -> None:
        self._detached_addon_review_window = window
        self._surfaces = _DummySurfaces(detached=detached)
        self.tabs = _Tabs()
        self.focus_calls = 0

    def _app_helpers(self) -> Any:
        return SimpleNamespace(surfaces=lambda: self._surfaces)

    def _focus_detached_addon_review_window(self) -> None:
        self.focus_calls += 1


def test_is_benchmark_detached_requires_live_window() -> None:
    assert _BenchmarkHarness(window=_DummyWindow(exists=True), detached=True)._is_benchmark_detached() is True
    assert _BenchmarkHarness(window=_DummyWindow(exists=False), detached=True)._is_benchmark_detached() is False
    assert _BenchmarkHarness(window=None, detached=True)._is_benchmark_detached() is False
    assert _BenchmarkHarness(window=_DummyWindow(exists=True), detached=False)._is_benchmark_detached() is False


def test_open_addon_review_tab_focuses_live_detached_window_only() -> None:
    harness = _AddonReviewHarness(window=_DummyWindow(exists=True), detached=True)

    harness._open_addon_review_tab()

    assert harness.focus_calls == 1
    assert harness.tabs.selected == []


def test_open_addon_review_tab_falls_back_to_main_tab_when_window_handle_is_stale() -> None:
    harness = _AddonReviewHarness(window=_DummyWindow(exists=False), detached=True)

    harness._open_addon_review_tab()

    assert harness.focus_calls == 0
    assert harness.tabs.selected == [t("gui.tab.addon_review")]