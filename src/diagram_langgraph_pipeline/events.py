"""Credential-free progress events for interactive and scripted runs."""

from __future__ import annotations

from threading import Lock
from typing import Callable

from .contracts import RunEvent


class NullEventSink:
    def emit(self, event: RunEvent) -> None:
        return None


class CallbackEventSink:
    def __init__(self, callback: Callable[[RunEvent], None]) -> None:
        self._callback = callback
        self._lock = Lock()

    def emit(self, event: RunEvent) -> None:
        with self._lock:
            self._callback(event)


class RecordingEventSink:
    def __init__(self, callback: Callable[[RunEvent], None] | None = None) -> None:
        self._callback = callback
        self._events: list[RunEvent] = []
        self._lock = Lock()

    def emit(self, event: RunEvent) -> None:
        with self._lock:
            self._events.append(event)
            if self._callback:
                self._callback(event)

    def snapshot(self) -> list[RunEvent]:
        with self._lock:
            return list(self._events)
