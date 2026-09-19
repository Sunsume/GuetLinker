"""Tests for instantaneous network-throughput sampling and formatting."""

from types import SimpleNamespace

import pytest

from src.core.network_speed import (
    NetworkSpeed,
    NetworkSpeedSampler,
    format_bytes_per_second,
)


def test_sampler_uses_counter_and_monotonic_time_deltas():
    counters = iter(
        [
            SimpleNamespace(bytes_sent=1000, bytes_recv=2000),
            SimpleNamespace(bytes_sent=3048, bytes_recv=6096),
        ]
    )
    timestamps = iter([10.0, 12.0])
    sampler = NetworkSpeedSampler(
        counter_reader=lambda: next(counters),
        clock=lambda: next(timestamps),
    )

    assert sampler.sample() == NetworkSpeed()
    assert sampler.sample() == NetworkSpeed(
        download_bps=2048,
        upload_bps=1024,
    )


def test_sampler_restarts_cleanly_after_counter_reset():
    counters = iter(
        [
            SimpleNamespace(bytes_sent=5000, bytes_recv=9000),
            SimpleNamespace(bytes_sent=100, bytes_recv=200),
        ]
    )
    timestamps = iter([1.0, 2.0])
    sampler = NetworkSpeedSampler(
        counter_reader=lambda: next(counters),
        clock=lambda: next(timestamps),
    )

    sampler.sample()

    assert sampler.sample() == NetworkSpeed()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0 B/s"),
        (512, "512 B/s"),
        (1024, "1.00 KB/s"),
        (12.5 * 1024, "12.5 KB/s"),
        (128 * 1024, "128 KB/s"),
        (2.5 * 1024 * 1024, "2.50 MB/s"),
    ],
)
def test_speed_formatting(value, expected):
    assert format_bytes_per_second(value) == expected
