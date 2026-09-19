"""Lightweight system-wide network throughput sampling."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import psutil

logger = logging.getLogger("guetlinker.network_speed")


class _NetworkCounters(Protocol):
    bytes_sent: int
    bytes_recv: int


@dataclass(frozen=True)
class NetworkSpeed:
    """Instantaneous system-wide transfer rates in bytes per second."""

    download_bps: float = 0.0
    upload_bps: float = 0.0


def format_bytes_per_second(value: float) -> str:
    """Format a bytes-per-second value using compact binary units."""
    amount = max(0.0, float(value))
    units = ("B/s", "KB/s", "MB/s", "GB/s", "TB/s")
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B/s":
                return f"{amount:.0f} {unit}"
            if amount >= 100:
                return f"{amount:.0f} {unit}"
            if amount >= 10:
                return f"{amount:.1f} {unit}"
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return "0 B/s"


class NetworkSpeedSampler:
    """Calculate transfer rates from successive cumulative byte counters."""

    def __init__(
        self,
        counter_reader: Callable[[], _NetworkCounters | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._counter_reader = counter_reader or self._read_system_counters
        self._clock = clock
        self._previous: tuple[int, int, float] | None = None

    @staticmethod
    def _read_system_counters() -> _NetworkCounters | None:
        return psutil.net_io_counters(nowrap=True)

    def reset(self) -> None:
        """Discard the previous baseline before restarting sampling."""
        self._previous = None

    def sample(self) -> NetworkSpeed:
        """Return speed since the previous sample, or zero for a new baseline."""
        try:
            counters = self._counter_reader()
        except (OSError, RuntimeError):
            logger.debug("Unable to read network byte counters", exc_info=True)
            return NetworkSpeed()

        if counters is None:
            return NetworkSpeed()

        now = self._clock()
        sent = int(counters.bytes_sent)
        received = int(counters.bytes_recv)
        previous = self._previous
        self._previous = (sent, received, now)

        if previous is None:
            return NetworkSpeed()

        previous_sent, previous_received, previous_time = previous
        elapsed = now - previous_time
        if (
            elapsed <= 0
            or sent < previous_sent
            or received < previous_received
        ):
            return NetworkSpeed()

        return NetworkSpeed(
            download_bps=(received - previous_received) / elapsed,
            upload_bps=(sent - previous_sent) / elapsed,
        )
