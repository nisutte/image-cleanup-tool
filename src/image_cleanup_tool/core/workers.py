import threading
import time
from queue import Queue, Empty
from typing import Tuple
from pathlib import Path
from typing import List, Dict, Union

from ..api.openai_api import load_and_encode_image, analyze_image


class RateLimiter:
    """Simple rate limiter to enforce max calls per period across threads."""

    def __init__(self, max_calls: int, period: float = 60.0) -> None:
        self.interval = period / max_calls if max_calls > 0 else 0
        self.lock = threading.Lock()
        self.next_allowed = time.monotonic()

    def wait(self) -> None:
        """Block until the next call is allowed."""
        with self.lock:
            now = time.monotonic()
            if self.next_allowed > now:
                time.sleep(self.next_allowed - now)
                now = time.monotonic()
            self.next_allowed = now + self.interval


class WorkerPool:
    """
    Worker pool to analyze images in parallel with rate limiting.

    Attributes:
        results: Dict[Path, Union[dict, Exception]]
    """

    def __init__(
        self,
        image_paths: List[Path],
        num_workers: int = 8,
        requests_per_minute: int = 60,
        size: int = 512,
    ) -> None:
        self.image_paths = list(image_paths)
        self.num_workers = max(1, num_workers)
        self.requests_per_minute = requests_per_minute
        self.size = size
        self.queue: Queue[Path] = Queue()
        # results dict for lookup, and a results queue for streaming
        self.results: Dict[Path, Union[dict, Exception]] = {}
        self.results_queue: Queue[Tuple[Path, Union[dict, Exception]]] = Queue()
        self._threads: List[threading.Thread] = []

    def start(self) -> None:
        """Populate queue and start worker threads."""
        for path in self.image_paths:
            self.queue.put(path)
        limiter = RateLimiter(self.requests_per_minute, period=60.0)
        for _ in range(self.num_workers):
            t = threading.Thread(target=self._worker, args=(limiter,), daemon=True)
            t.start()
            self._threads.append(t)

    def _worker(self, limiter: RateLimiter) -> None:
        """Thread target: process images until queue is empty."""
        while True:
            try:
                path = self.queue.get(block=False)
            except Empty:
                break
            try:
                limiter.wait()
                b64 = load_and_encode_image(str(path), self.size)
                result = analyze_image(b64)
            except Exception as e:
                result = e
            # store and enqueue result
            self.results[path] = result
            self.results_queue.put((path, result))
            # signal task completion
            self.queue.task_done()

    def join(self) -> None:
        """Wait for all tasks and threads to complete."""
        self.queue.join()
        for t in self._threads:
            t.join()

    def get_results(
        self,
        block: bool = False,
        timeout: float = None,
    ) -> List[Tuple[Path, Union[dict, Exception]]]:
        """
        Retrieve analysis results from the queue.

        Args:
            block: If True, wait for at least one result (with optional timeout).
            timeout: Maximum seconds to wait if block is True; ignored otherwise.

        Returns:
            A list of (Path, result) tuples drained from the results queue.
        """
        results: List[Tuple[Path, Union[dict, Exception]]] = []
        try:
            if block:
                item = self.results_queue.get(timeout=timeout)
                results.append(item)
            while True:
                item = self.results_queue.get_nowait()
                results.append(item)
        except Empty:
            pass
        return results

    def analyze_all(self) -> Queue:
        """Convenience: analyze all images, then return a queue of (path, result) tuples."""
        self.start()
        self.join()
        return self.results_queue
