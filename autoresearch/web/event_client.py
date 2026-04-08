import requests
import json
from typing import Generator, Optional
import threading
import queue


class EventClient:
    def __init__(self, url: str, poll_interval: float = 0.5):
        self.url = url
        self.poll_interval = poll_interval
        self.q: queue.Queue = queue.Queue()
        self._stop = threading.Event()

    def stream(self) -> Generator[dict, None, None]:
        """Poll the event endpoint and yield events."""
        while not self._stop.is_set():
            try:
                resp = requests.get(self.url, timeout=5)
                if resp.status_code == 200:
                    for line in resp.text.strip().split("\n"):
                        if line:
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError:
                                pass
                elif resp.status_code == 404:
                    # No events yet, wait
                    pass
            except requests.RequestException:
                pass
            self._stop.wait(self.poll_interval)

    def stop(self):
        self._stop.set()
