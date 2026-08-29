"""
metrics/metrics_logger.py - Step 6: Performance & Scale

Logs metrics periodically.
"""

import logging
import threading
import time

logger = logging.getLogger("metrics_logger")

class MetricsLogger:
    def __init__(self, perf_counter, interval=10):
        self.perf_counter = perf_counter
        self.interval = interval
        self.thread = None
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._log_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if self.thread:
            self.thread.join()

    def _log_loop(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.interval):
                break
            fps = self.perf_counter.get_fps()
            avg_time = self.perf_counter.get_avg_processing_time()
            logger.info(f"[Metrics] FPS: {fps:.2f} | Avg processing time: {avg_time*1000:.2f} ms")
