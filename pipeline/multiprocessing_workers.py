"""
pipeline/multiprocessing_workers.py - Step 6: Performance & Scale

Runs the pipeline in a background process so the main process can run the API server.

Windows uses the 'spawn' multiprocessing start method, which requires all
arguments to be picklable. Since DetectionPipeline contains unpicklable
objects (cv2.VideoCapture, YOLO models, PaddleOCR), we use a factory
function pattern: the worker receives a *callable that builds* the pipeline
inside the child process, rather than a pre-built pipeline instance.
"""

import multiprocessing
import logging
from typing import Callable

logger = logging.getLogger("multiprocessing_workers")


class PipelineWorker:
    def __init__(self, target: Callable, *args, **kwargs):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.process = None
        self._stop_event = multiprocessing.Event()

    def start(self):
        logger.info("Starting pipeline worker process...")
        self.process = multiprocessing.Process(
            target=self._run_with_shutdown,
            args=(self.target, self._stop_event) + self.args,
            kwargs=self.kwargs,
            daemon=True
        )
        self.process.start()
        logger.info(f"Pipeline worker started with PID: {self.process.pid}")

    @staticmethod
    def _run_with_shutdown(target, stop_event, *args, **kwargs):
        """Wrapper that passes the stop event to the target function."""
        try:
            target(*args, **kwargs)
        except Exception:
            logging.getLogger("multiprocessing_workers").exception(
                "Pipeline worker crashed with unhandled exception"
            )

    def stop(self, timeout: float = 10.0):
        if self.process and self.process.is_alive():
            logger.info("Requesting graceful pipeline shutdown...")
            self._stop_event.set()
            self.process.join(timeout=timeout)
            if self.process.is_alive():
                logger.warning("Worker did not stop gracefully, terminating...")
                self.process.terminate()
                self.process.join()
            logger.info("Pipeline worker stopped.")
