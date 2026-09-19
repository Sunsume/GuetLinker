"""Input-source detection and live password-field reminder behavior."""

from types import SimpleNamespace

import pytest

from src.core import input_method
from src.ui import input_method_hint
from src.ui.self_service_login_dialog import SelfServiceLoginDialog
from src.ui.settings_page import SettingsPage


@pytest.mark.parametrize(
    ("language", "expected"),
    [("zh-Hans", True), ("zh-Hant", True), ("en", False), ("ja", False)],
)
def test_macos_uses_selected_input_source_language(monkeypatch, language, expected):
    monkeypatch.setattr(input_method.sys, "platform", "darwin")
    monkeypatch.setattr(
        input_method, "_macos_input_source",
        lambda: SimpleNamespace(language=lambda: language),
    )
    assert input_method.is_chinese_input_active() is expected


@pytest.mark.parametrize(
    ("page_type", "other_field"),
    [(SettingsPage, "_user_id_input"), (SelfServiceLoginDialog, "_account_input")],
)
def test_hint_tracks_focus_and_input_switch_without_editing_password(
    qtbot, monkeypatch, page_type, other_field,
):
    state = {"chinese": True}
    monkeypatch.setattr(
        input_method_hint, "is_chinese_input_active", lambda: state["chinese"]
    )
    page = page_type()
    qtbot.addWidget(page)
    page.show()
    page.activateWindow()
    editor = page._password_input
    hint = page._password_input_hint
    editor.setText("Example.123")
    editor.setFocus()
    qtbot.waitUntil(hint.isVisible)
    assert "中文输入法" in hint.text()

    state["chinese"] = False
    qtbot.waitUntil(lambda: not hint.isVisible())
    state["chinese"] = True
    qtbot.waitUntil(hint.isVisible)

    getattr(page, other_field).setFocus()
    qtbot.waitUntil(lambda: not hint.isVisible())
    assert not hint._timer.isActive()
    assert editor.text() == "Example.123"

    editor.setFocus()
    qtbot.waitUntil(hint.isVisible)
    page.hide()
    assert not hint._timer.isActive()
