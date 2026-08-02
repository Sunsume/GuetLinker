"""Tests for the process-wide single-instance guard."""

from __future__ import annotations

import uuid

from src.core.single_instance import SingleInstanceGuard


def test_only_one_guard_can_own_the_same_process_lock():
    name = f"GuetLinker.Test.{uuid.uuid4().hex}"
    first = SingleInstanceGuard(name)
    second = SingleInstanceGuard(name)
    replacement = SingleInstanceGuard(name)

    try:
        assert first.acquire() is True
        assert second.acquire() is False
        first.release()
        assert replacement.acquire() is True
    finally:
        first.release()
        second.release()
        replacement.release()
