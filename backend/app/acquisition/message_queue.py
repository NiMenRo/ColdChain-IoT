from collections import deque
from typing import Optional


class MessageQueue:

    def __init__(self, max_size: int = 1000):
        self._queue: deque = deque(maxlen=max_size)

    def append(self, message: dict) -> None:
        self._queue.append(message)

    def pop(self) -> Optional[dict]:
        if self._queue:
            return self._queue.popleft()
        return None

    def get_all(self) -> list:
        return list(self._queue)

    def clear(self) -> None:
        self._queue.clear()
