"""
metrics/perf_counters.py - Step 6: Performance & Scale

Tracks FPS, processing time, etc.
"""

import time
import threading
from collections import deque

class PerfCounter:
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.processing_times = deque(maxlen=window_size)
        self.lock = threading.Lock()
        self._local = threading.local()
        self.frames_processed = 0

    def start_frame(self):
        self._local.start_time = time.perf_counter()

    def end_frame(self):
        start = getattr(self._local, 'start_time', None)
        if start is not None:
            elapsed = time.perf_counter() - start
            with self.lock:
                self.processing_times.append(elapsed)
                self.frames_processed += 1
            self._local.start_time = None

    def get_fps(self):
        with self.lock:
            avg_time = self.get_avg_processing_time()
            return 1.0 / avg_time if avg_time > 0 else 0.0

    def get_avg_processing_time(self):
        with self.lock:
            if not self.processing_times:
                return 0.0
            return sum(self.processing_times) / len(self.processing_times)
