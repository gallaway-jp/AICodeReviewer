# src/aicodereviewer/performance.py
import time
import psutil
import os
from typing import Dict, Any
from contextlib import contextmanager

from .config import config

class PerformanceMonitor:
    """Monitor performance metrics during code review operations"""

    def __init__(self):
        self.metrics = {}
        self.enabled = config.get('logging', 'enable_performance_logging', False)

    @contextmanager
    def track_operation(self, operation_name: str):
        """Context manager to track operation performance"""
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

            print(f"Performance: {operation_name} took {duration:.2f}s, "
                  f"memory change: {memory_delta / (1024*1024):.2f}MB")

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected performance metrics"""
        return self.metrics.copy()

    def reset(self):
        """Reset performance metrics"""
        self.metrics.clear()

# Global performance monitor instance
performance_monitor = PerformanceMonitor()