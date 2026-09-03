import multiprocessing
import multiprocessing.synchronize
import logging
from typing import Callable, Any
from multiprocessing import Queue

logger = logging.getLogger("workers")

import threading

class MasterOcrProcess:
    def __init__(self, run_func: Callable[[Queue], None], ocr_queue: Queue):
        self.run_func = run_func
        self.ocr_queue = ocr_queue
        self._process: multiprocessing.Process | None = None
        self._stop_event = multiprocessing.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._process is not None and self._process.is_alive():
                logger.warning("Master OCR Process is already running.")
                return

            self._stop_event.clear()
            self._process = multiprocessing.Process(
                target=self._run_wrapper,
                args=(self.run_func, self.ocr_queue, self._stop_event),
                daemon=True
            )
            self._process.start()
            logger.info(f"Master OCR Process started (PID: {self._process.pid})")

    def stop(self):
        with self._lock:
            self._stop_event.set()
            if self._process is not None:
                self._process.join(timeout=3.0)
                if self._process and self._process.is_alive():
                    logger.warning(f"Master OCR Process {self._process.pid} hung. Terminating.")
                    self._process.terminate()
                self._process = None

    def is_alive(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.is_alive()

    @staticmethod
    def _run_wrapper(run_func: Callable, queue: Queue, stop_event: multiprocessing.synchronize.Event):
        try:
            run_func(queue, stop_event)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(f"Fatal error in Master OCR worker: {e}")

class CameraFeederProcess:
    def __init__(self, run_func: Callable, camera_id: int, source_url: str, camera_name: str, mode: str, ocr_queue: Queue):
        self.run_func = run_func
        self.camera_id = camera_id
        self.source_url = source_url
        self.camera_name = camera_name
        self.mode = mode
        self.ocr_queue = ocr_queue
        self._process: multiprocessing.Process | None = None
        self._stop_event = multiprocessing.Event()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._process is not None and self._process.is_alive():
                return
            
            self._stop_event.clear()
            self._process = multiprocessing.Process(
                target=self._run_wrapper,
                args=(self.run_func, self.camera_id, self.source_url, self.camera_name, self.mode, self.ocr_queue, self._stop_event),
                daemon=True
            )
            self._process.start()
            logger.info(f"Camera Feeder {self.camera_id} started (PID: {self._process.pid})")

    def stop(self):
        with self._lock:
            self._stop_event.set()
            if self._process is not None:
                self._process.join(timeout=5.0)
                if self._process and self._process.is_alive():
                    logger.warning(f"Feeder {self.camera_id} hung. Terminating.")
                    self._process.terminate()
                self._process = None

    def is_alive(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.is_alive()

    def is_crashed(self) -> bool:
        """Check if the process exited abnormally (non-zero exit code)."""
        with self._lock:
            return (self._process is not None and
                    not self._process.is_alive() and
                    self._process.exitcode not in (None, 0))

    @staticmethod
    def _run_wrapper(run_func, camera_id, source_url, camera_name, mode, ocr_queue, stop_event):
        try:
            run_func(camera_id, source_url, camera_name, mode, ocr_queue, stop_event)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(f"Fatal error in feeder {camera_id}: {e}")
            try:
                from db.dao_cameras import update_camera_status
                update_camera_status(camera_id, "error")
            except Exception:
                pass

