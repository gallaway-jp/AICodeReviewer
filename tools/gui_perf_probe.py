#!/usr/bin/env python3
"""Manual performance probe for AICodeReviewer GUI resize responsiveness."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import logging
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import customtkinter as ctk  # type: ignore[import-untyped]

# Ensure src is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from aicodereviewer.gui.app import App
from aicodereviewer.gui.test_fixtures import apply_test_config, create_sample_issues
from aicodereviewer.i18n import t

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _windows_monitor_inventory() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []

    user32 = ctypes.windll.user32
    monitors: list[dict[str, Any]] = []

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    get_dpi_for_monitor = None
    try:
        get_dpi_for_monitor = ctypes.windll.shcore.GetDpiForMonitor
    except Exception:
        get_dpi_for_monitor = None

    def _callback(monitor: Any, _hdc: Any, _rect: Any, _data: Any) -> int:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        entry = {
            "handle": int(ctypes.cast(monitor, ctypes.c_void_p).value or 0),
            "device": info.szDevice,
            "monitor": (info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom),
            "work": (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom),
            "primary": bool(info.dwFlags & 1),
        }
        if get_dpi_for_monitor is not None:
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            if get_dpi_for_monitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                entry["dpi"] = (int(dpi_x.value), int(dpi_y.value))
        monitors.append(entry)
        return 1

    callback = monitor_enum_proc(_callback)
    user32.EnumDisplayMonitors(0, 0, callback, 0)
    return monitors


def _describe_window_monitor(app: Any, monitors: list[dict[str, Any]]) -> dict[str, Any]:
    if platform.system() != "Windows" or not monitors:
        return {}

    hwnd = int(app.winfo_id())
    user32 = ctypes.windll.user32
    monitor_handle = int(user32.MonitorFromWindow(hwnd, 2))
    scaling = None
    try:
        import customtkinter as ctk  # type: ignore[import-untyped]

        scaling = float(ctk.ScalingTracker.get_window_scaling(app))
    except Exception:
        scaling = None

    match = next((monitor for monitor in monitors if monitor.get("handle") == monitor_handle), None)
    return {
        "handle": monitor_handle,
        "device": match.get("device") if match else None,
        "dpi": match.get("dpi") if match else None,
        "monitor": match.get("monitor") if match else None,
        "scaling": scaling,
    }


def _format_stats(durations: list[float]) -> str:
    if not durations:
        return "no measurements"
    return (
        f"count={len(durations)}, min={min(durations):.3f}s, "
        f"avg={sum(durations)/len(durations):.3f}s, max={max(durations):.3f}s"
    )


def _tab_name_map() -> dict[str, str]:
    return {
        "review": t("gui.tab.review"),
        "settings": t("gui.tab.settings"),
        "benchmarks": t("gui.tab.benchmarks"),
        "results": t("gui.tab.results"),
        "log": t("gui.tab.log"),
        "addon_review": t("gui.tab.addon_review"),
    }


def run_probe(app: Any, widths: list[int], heights: list[int], rounds: int, pause_ms: int, *, auto_close_ms: int) -> None:
    logger.info("Starting GUI resize performance probe")
    durations: list[float] = []

    def _probe() -> None:
        for index in range(rounds):
            width = widths[index % len(widths)]
            height = heights[index % len(heights)]
            start = time.perf_counter()
            app.geometry(f"{width}x{height}")
            app.update_idletasks()
            app.update()
            durations.append(time.perf_counter() - start)
            logger.info(
                "[%d/%d] geometry=%dx%d took %.3fs",
                index + 1,
                rounds,
                width,
                height,
                durations[-1],
            )
            time.sleep(pause_ms / 1000.0)

        logger.info("Probe complete: %s", _format_stats(durations))
        if hasattr(app, "_configure_metrics_snapshot"):
            snapshot = app._configure_metrics_snapshot()
            logger.info("Configure event snapshot: %s", snapshot)
        if auto_close_ms > 0:
            logger.info("Auto-closing probe window in %d ms.", auto_close_ms)
            app.after(auto_close_ms, app.destroy)
        else:
            logger.info("Close the window or press Ctrl+C to exit.")

    app.after(250, _probe)


def run_monitor_move_probe(
    app: Any,
    *,
    rounds: int,
    pause_ms: int,
    window_size: tuple[int, int],
    auto_close_ms: int,
    tabs_to_probe: list[str] | None,
) -> None:
    monitors = _windows_monitor_inventory()
    logger.info("Detected monitors: %s", monitors or "unavailable")

    if len(monitors) < 2:
        logger.info("Monitor move probe requires at least two displays; skipping automated cross-screen move loop.")
        logger.info("Open the app on a multi-monitor setup and drag it across screens while watching the configure snapshot.")
        if auto_close_ms > 0:
            app.after(auto_close_ms, app.destroy)
        return

    width, height = window_size
    positions: list[tuple[int, int, dict[str, Any]]] = []
    for monitor in monitors[:2]:
        left, top, right, bottom = monitor["work"]
        centered_x = left + max(0, ((right - left) - width) // 2)
        centered_y = top + max(0, ((bottom - top) - height) // 2)
        positions.append((centered_x, centered_y, monitor))

    durations: list[float] = []
    selected_tabs = tabs_to_probe or ["review"]
    tab_map = _tab_name_map()

    def _probe() -> None:
        if "results" in selected_tabs:
            app._show_issues(create_sample_issues())

        for tab_key in selected_tabs:
            tab_name = tab_map.get(tab_key)
            if not tab_name:
                logger.info("Skipping unknown tab key: %s", tab_key)
                continue
            previous_monitor: int | None = None
            app.tabs.set(tab_name)
            app.update_idletasks()
            app.update()
            if hasattr(app, "_reset_configure_metrics"):
                app._reset_configure_metrics()
            tab_durations: list[float] = []
            logger.info("Starting monitor move probe for tab=%s", tab_key)
            for index in range(rounds):
                x, y, target = positions[index % len(positions)]
                start = time.perf_counter()
                app.geometry(f"{width}x{height}+{x}+{y}")
                app.update_idletasks()
                app.update()
                duration = time.perf_counter() - start
                durations.append(duration)
                tab_durations.append(duration)
                current_monitor = _describe_window_monitor(app, monitors)
                monitor_handle = current_monitor.get("handle")
                changed = " monitor-change" if monitor_handle != previous_monitor else ""
                previous_monitor = monitor_handle
                logger.info(
                    "[%s %d/%d] move target=%s geometry=%dx%d+%d+%d took %.3fs%s state=%s",
                    tab_key,
                    index + 1,
                    rounds,
                    target.get("device"),
                    width,
                    height,
                    x,
                    y,
                    duration,
                    changed,
                    current_monitor,
                )
                time.sleep(pause_ms / 1000.0)
            logger.info("Tab %s monitor move stats: %s", tab_key, _format_stats(tab_durations))
            if hasattr(app, "_configure_metrics_snapshot"):
                logger.info("Tab %s configure snapshot: %s", tab_key, app._configure_metrics_snapshot())

        logger.info("Monitor move probe complete: %s", _format_stats(durations))
        if auto_close_ms > 0:
            logger.info("Auto-closing probe window in %d ms.", auto_close_ms)
            app.after(auto_close_ms, app.destroy)
        else:
            logger.info("Close the window or press Ctrl+C to exit.")

    app.after(250, _probe)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch a manual GUI probe that drives window resize events and measures response time.",
    )
    parser.add_argument("--rounds", type=int, default=10, help="Number of resize measurements to capture")
    parser.add_argument("--pause-ms", type=int, default=100, help="Delay between resize samples")
    parser.add_argument("--widths", type=str, default="960,1280,1600", help="Comma-separated widths to cycle")
    parser.add_argument("--heights", type=str, default="720,820,940", help="Comma-separated heights to cycle")
    parser.add_argument("--move-across-monitors", action="store_true", help="Move the window across detected monitors instead of resizing it")
    parser.add_argument("--move-width", type=int, default=1180, help="Window width for monitor-move probe")
    parser.add_argument("--move-height", type=int, default=820, help="Window height for monitor-move probe")
    parser.add_argument("--auto-close-ms", type=int, default=250, help="Automatically close the probe window after the run completes; set to 0 to keep it open")
    parser.add_argument("--tabs", type=str, default="review", help="Comma-separated tab keys for monitor probe: review,settings,benchmarks,results,log,addon_review")
    parser.add_argument("--disable-dpi-awareness", action="store_true", help="Disable CustomTkinter automatic DPI awareness before creating the app")
    args = parser.parse_args()

    apply_test_config()
    if args.disable_dpi_awareness:
        ctk.deactivate_automatic_dpi_awareness()
    app = App(testing_mode=True)
    app.title("AICodeReviewer GUI Perf Probe")

    def _report_callback_exception(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("Tk callback failure:\n%s", formatted.rstrip())

    app.report_callback_exception = _report_callback_exception

    widths = [int(w.strip()) for w in args.widths.split(",") if w.strip().isdigit()]
    heights = [int(h.strip()) for h in args.heights.split(",") if h.strip().isdigit()]
    if not widths or not heights:
        raise ValueError("At least one width and one height are required")

    if args.move_across_monitors:
        tab_keys = [tab.strip().lower() for tab in args.tabs.split(",") if tab.strip()]
        run_monitor_move_probe(
            app,
            rounds=args.rounds,
            pause_ms=args.pause_ms,
            window_size=(args.move_width, args.move_height),
            auto_close_ms=args.auto_close_ms,
            tabs_to_probe=tab_keys,
        )
    else:
        run_probe(app, widths, heights, args.rounds, args.pause_ms, auto_close_ms=args.auto_close_ms)
    app.mainloop()


if __name__ == "__main__":
    main()
