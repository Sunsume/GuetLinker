"""Tests for persistent diagnostic-log helpers."""

from src.core.logger import read_recent_log


def test_read_recent_log_returns_only_requested_tail(tmp_path):
    log_file = tmp_path / "guetlinker.log"
    log_file.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    assert read_recent_log(max_lines=2, path=log_file) == "three\nfour"


def test_read_recent_log_handles_missing_file(tmp_path):
    assert read_recent_log(path=tmp_path / "missing.log") == ""
