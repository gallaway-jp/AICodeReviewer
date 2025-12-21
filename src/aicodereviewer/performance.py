# src/aicodereviewer/performance.py
"""
Performance monitoring utilities for AICodeReviewer.

This module provides optional performance tracking for code review operations,
including timing and memory usage monitoring to help optimize the application.

Classes:
    PerformanceMonitor: Context manager for tracking operation performance
"""
import time
import psutil
import os
import logging
from typing import Dict, Any
from contextlib import contextmanager

from .config import config
logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Monitor performance metrics during code review operations.

    Tracks execution time and memory usage for operations when enabled.
    Uses psutil for accurate memory measurements and provides detailed
    metrics for performance analysis and optimization.

    Attributes:
        metrics (Dict[str, Any]): Collected performance metrics
        enabled (bool): Whether performance monitoring is active
    """

    def __init__(self):
        """
        Initialize performance monitor with configuration settings.

        Checks configuration to determine if performance logging is enabled.
        """
        self.metrics = {}
        self.enabled = config.get('logging', 'enable_performance_logging', False)

    @contextmanager
    def track_operation(self, operation_name: str):
        """
        Context manager to track operation performance metrics.

        Measures execution time and memory usage for the wrapped operation.
        Only collects metrics when performance monitoring is enabled.

        Args:
            operation_name (str): Name identifier for the operation being tracked

        Example:
            with performance_monitor.track_operation("file_scan"):
                scan_project_files()
        """
        if not self.enabled:
            yield
            return

        start_time = time.time()
        start_memory = psutil.Process(os.getpid()).memory_info().rss

        try:
            yield
        finally:
            end_time = time.time()
            end_memory = psutil.Process(os.getpid()).memory_info().rss

            duration = end_time - start_time
            memory_delta = end_memory - start_memory

            self.metrics[operation_name] = {
                'duration_seconds': duration,
                'memory_delta_bytes': memory_delta,
                'memory_delta_mb': memory_delta / (1024 * 1024)
            }

            logger.info(
                f"Performance: {operation_name} took {duration:.2f}s, memory change: {memory_delta / (1024*1024):.2f}MB"
            )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get collected performance metrics.

        Returns a copy of all collected metrics to prevent external modification.

        Returns:
            Dict[str, Any]: Dictionary of operation names to performance metrics
        """
        return self.metrics.copy()

    def reset(self):
        """Reset performance metrics to start fresh collection."""
        self.metrics.clear()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()