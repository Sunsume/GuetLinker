"""UI tests for the About page project entry point."""

from PySide6.QtGui import QDesktopServices

from src.ui.about_page import AboutPage, PROJECT_URL


def test_about_page_exposes_clickable_github_project(qapp, monkeypatch):
    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    page = AboutPage()

    assert page._project_button.text() == "访问我们的项目"
    assert page._project_button.icon().isNull() is False
    assert page._project_button.isFlat() is True
    assert page._project_button.toolTip() == PROJECT_URL

    page._project_button.click()

    assert opened_urls == [PROJECT_URL]
