"""Injectable clock and ID helpers for deterministic tests."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from typing import Callable
from uuid import uuid4


class Clock:
    def __init__(self, fixed: datetime | None = None) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        if self._fixed is not None:
            return self._fixed
        return datetime.now(UTC)

    def set(self, value: datetime) -> None:
        self._fixed = value


class IdFactory:
    def __init__(self, deterministic: bool = False) -> None:
        self._deterministic = deterministic
        self._counters: dict[str, count] = {}

    def __call__(self, prefix: str) -> str:
        if not self._deterministic:
            return f"{prefix}_{uuid4().hex[:16]}"
        counter = self._counters.setdefault(prefix, count(1))
        return f"{prefix}_{next(counter):04d}"


ClockFn = Callable[[], datetime]
IdFn = Callable[[str], str]
