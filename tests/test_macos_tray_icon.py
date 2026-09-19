"""Tests for compact macOS menu-bar speed formatting."""

import pytest

from src.ui.macos_tray_icon import format_menu_speed


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0K"),
        (512, "<1K"),
        (1024, "1.0K"),
        (57.7 * 1024, "57.7K"),
        (200 * 1024, "200K"),
        (12.5 * 1024 * 1024, "12.5M"),
        (999 * 1024 * 1024, "999M"),
        (2.5 * 1024 * 1024 * 1024, "2.5G"),
    ],
)
def test_menu_speed_is_compact_and_stable(value, expected):
    formatted = format_menu_speed(value)

    assert formatted == expected
    assert len(formatted) <= 5
