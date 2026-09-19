"""Native macOS menu-bar status item with live network throughput."""

from __future__ import annotations

import logging

import objc
from AppKit import (
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSForegroundColorAttributeName,
    NSImage,
    NSImageOnly,
    NSMenu,
    NSMenuItem,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSStatusBar,
    NSString,
    NSTextAlignmentRight,
    NSUserNotification,
    NSUserNotificationCenter,
    NSVariableStatusItemLength,
)
from Foundation import NSMakeRect, NSMakeSize, NSObject
from PySide6.QtCore import QObject
from PySide6.QtGui import QAction

from src.core.monitor import NetworkStatus
from src.core.network_speed import NetworkSpeed, format_bytes_per_second
from src.core.portal import PortalSession

logger = logging.getLogger("guetlinker.ui.macos_tray")

MENU_BAR_ITEM_WIDTH = 56.0
MENU_BAR_ITEM_HEIGHT = 22.0


def format_menu_speed(bytes_per_second: float) -> str:
    """Return a stable, at-most-five-character menu-bar speed value."""
    amount = max(0.0, float(bytes_per_second))
    if amount < 1024:
        return "0K" if amount < 1 else "<1K"

    amount /= 1024
    for unit in ("K", "M", "G", "T"):
        if amount < 1024 or unit == "T":
            if amount < 10:
                return f"{amount:.1f}{unit}"
            if amount < 100:
                return f"{amount:.1f}{unit}"
            return f"{amount:.0f}{unit}"
        amount /= 1024
    return "0K"


class _MenuTarget(NSObject):
    """Objective-C target forwarding native menu actions to Qt actions."""

    owner = objc.ivar()

    def initWithOwner_(self, owner):
        self = objc.super(_MenuTarget, self).init()
        if self is not None:
            self.owner = owner
        return self

    @objc.IBAction
    def showWindow_(self, _sender) -> None:
        self.owner.show_action.trigger()

    @objc.IBAction
    def checkNow_(self, _sender) -> None:
        self.owner.check_action.trigger()

    @objc.IBAction
    def connectNetwork_(self, _sender) -> None:
        self.owner.connect_action.trigger()

    @objc.IBAction
    def disconnectNetwork_(self, _sender) -> None:
        self.owner.disconnect_action.trigger()

    @objc.IBAction
    def quitApplication_(self, _sender) -> None:
        self.owner.quit_action.trigger()


class MacOSTrayIcon(QObject):
    """A polished native status item for the macOS menu bar."""

    _STATUS_COLORS = {
        NetworkStatus.CONNECTED: NSColor.systemGreenColor,
        NetworkStatus.DISCONNECTED: NSColor.systemRedColor,
        NetworkStatus.RECONNECTING: NSColor.systemOrangeColor,
        NetworkStatus.UNKNOWN: NSColor.systemGrayColor,
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._status = NetworkStatus.UNKNOWN
        self._speed = NetworkSpeed()
        self._portal_session_online = False
        self._login_in_progress = False
        self._status_item = None
        self._button = None
        self._native_menu = None
        self._target = _MenuTarget.alloc().initWithOwner_(self)
        self._setup_actions()
        self._create_status_item()

    def _setup_actions(self) -> None:
        self._show_action = QAction("显示主窗口", self)
        self._check_action = QAction("立即检测", self)
        self._connect_action = QAction("连接", self)
        self._disconnect_action = QAction("断开", self)
        self._disconnect_action.setEnabled(False)
        self._quit_action = QAction("退出", self)

    def _create_status_item(self) -> None:
        if self._status_item is not None:
            return
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._button = self._status_item.button()
        self._button.setImagePosition_(NSImageOnly)
        self._status_item.setLength_(MENU_BAR_ITEM_WIDTH)

        self._native_menu = NSMenu.alloc().initWithTitle_("GuetLinker")
        self._native_menu.setAutoenablesItems_(False)
        self._show_item = self._add_menu_item("显示主窗口", "showWindow:")
        self._native_menu.addItem_(NSMenuItem.separatorItem())
        self._check_item = self._add_menu_item("立即检测", "checkNow:")
        self._connect_item = self._add_menu_item("连接", "connectNetwork:")
        self._disconnect_item = self._add_menu_item(
            "断开",
            "disconnectNetwork:",
        )
        self._native_menu.addItem_(NSMenuItem.separatorItem())
        self._quit_item = self._add_menu_item(
            "退出 GuetLinker",
            "quitApplication:",
            "q",
        )
        self._status_item.setMenu_(self._native_menu)
        self._update_presentation()
        self._update_action_states()

    def _add_menu_item(
        self,
        title: str,
        selector: str,
        shortcut: str = "",
    ):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title,
            selector,
            shortcut,
        )
        item.setTarget_(self._target)
        self._native_menu.addItem_(item)
        return item

    @property
    def show_action(self) -> QAction:
        return self._show_action

    @property
    def check_action(self) -> QAction:
        return self._check_action

    @property
    def connect_action(self) -> QAction:
        return self._connect_action

    @property
    def disconnect_action(self) -> QAction:
        return self._disconnect_action

    @property
    def quit_action(self) -> QAction:
        return self._quit_action

    def show(self) -> None:
        self._create_status_item()

    def hide(self) -> None:
        if self._status_item is not None:
            NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
            self._status_item = None
            self._button = None

    def update_status(self, status: NetworkStatus) -> None:
        self._status = status
        self._update_presentation()
        self._update_action_states()

    def update_portal_session(self, session: PortalSession) -> None:
        self._portal_session_online = session.is_online
        self._update_presentation()
        self._update_action_states()

    def update_network_speed(self, speed: NetworkSpeed) -> None:
        self._speed = speed
        self._update_presentation()

    def set_login_in_progress(self, in_progress: bool) -> None:
        self._login_in_progress = in_progress
        self._connect_action.setText("取消连接" if in_progress else "连接")
        if self._connect_item is not None:
            self._connect_item.setTitle_(
                "取消连接" if in_progress else "连接"
            )
        self._update_action_states()

    def show_notification(
        self,
        title: str,
        message: str,
        method: str = "tray",
    ) -> None:
        if method == "silent":
            return
        try:
            notification = NSUserNotification.alloc().init()
            notification.setTitle_(title)
            notification.setInformativeText_(message)
            NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(
                notification
            )
        except Exception:
            logger.info("Notification: %s — %s", title, message)

    def _update_presentation(self) -> None:
        if self._button is None:
            return
        download = format_menu_speed(self._speed.download_bps)
        upload = format_menu_speed(self._speed.upload_bps)
        color_factory = self._STATUS_COLORS.get(
            self._status,
            NSColor.systemGrayColor,
        )
        self._button.setImage_(
            self._render_status_image(
                color_factory(),
                download,
                upload,
                self._menu_bar_text_color(),
            )
        )

        status_text = {
            NetworkStatus.CONNECTED: "校园网已登录"
            if self._portal_session_online
            else "已连接",
            NetworkStatus.DISCONNECTED: "已断网",
            NetworkStatus.RECONNECTING: "重连中",
            NetworkStatus.UNKNOWN: "状态未知",
        }.get(self._status, "状态未知")
        download_full = format_bytes_per_second(self._speed.download_bps)
        upload_full = format_bytes_per_second(self._speed.upload_bps)
        tooltip = (
            f"GuetLinker — {status_text}\n"
            f"下载 {download_full} · 上传 {upload_full}"
        )
        self._button.setToolTip_(tooltip)
        self._button.setAccessibilityLabel_(
            f"GuetLinker，{status_text}，下载 {download_full}，上传 {upload_full}"
        )

    @staticmethod
    def _render_status_image(
        status_color,
        download: str,
        upload: str,
        value_color=None,
    ):
        """Draw a Retina-friendly two-row speed indicator for the menu bar."""
        image = NSImage.alloc().initWithSize_(
            NSMakeSize(MENU_BAR_ITEM_WIDTH, MENU_BAR_ITEM_HEIGHT)
        )
        image.lockFocusFlipped_(True)
        try:
            # A soft halo plus a crisp inner dot keeps the connection state
            # visible without overpowering the two speed rows.
            status_color.colorWithAlphaComponent_(0.22).setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(1.0, 6.0, 10.0, 10.0)
            ).fill()
            status_color.setFill()
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(3.0, 8.0, 6.0, 6.0)
            ).fill()

            arrow_font = NSFont.systemFontOfSize_weight_(
                8.5,
                NSFontWeightSemibold,
            )
            value_font = NSFont.monospacedDigitSystemFontOfSize_weight_(
                8.5,
                NSFontWeightMedium,
            )
            paragraph = NSMutableParagraphStyle.alloc().init()
            paragraph.setAlignment_(NSTextAlignmentRight)
            value_attributes = {
                NSFontAttributeName: value_font,
                NSForegroundColorAttributeName: value_color
                or NSColor.labelColor(),
                NSParagraphStyleAttributeName: paragraph,
            }

            NSString.stringWithString_("↓").drawAtPoint_withAttributes_(
                (13.0, 0.2),
                {
                    NSFontAttributeName: arrow_font,
                    NSForegroundColorAttributeName: NSColor.systemBlueColor(),
                },
            )
            NSString.stringWithString_(download).drawInRect_withAttributes_(
                NSMakeRect(20.0, 0.0, 33.0, 10.5),
                value_attributes,
            )
            NSString.stringWithString_("↑").drawAtPoint_withAttributes_(
                (13.0, 10.5),
                {
                    NSFontAttributeName: arrow_font,
                    NSForegroundColorAttributeName: NSColor.systemGreenColor(),
                },
            )
            NSString.stringWithString_(upload).drawInRect_withAttributes_(
                NSMakeRect(20.0, 10.3, 33.0, 10.5),
                value_attributes,
            )
        finally:
            image.unlockFocus()
        return image

    def _menu_bar_text_color(self):
        """Resolve readable text against the menu bar's current appearance."""
        appearance = self._button.effectiveAppearance()
        matched = appearance.bestMatchFromAppearancesWithNames_(
            [NSAppearanceNameAqua, NSAppearanceNameDarkAqua]
        )
        if matched == NSAppearanceNameDarkAqua:
            return NSColor.whiteColor()
        return NSColor.blackColor()

    def _update_action_states(self) -> None:
        can_connect = self._login_in_progress or self._status in {
            NetworkStatus.DISCONNECTED,
            NetworkStatus.UNKNOWN,
        }
        can_disconnect = (
            not self._login_in_progress
            and self._status == NetworkStatus.CONNECTED
            and self._portal_session_online
        )
        self._connect_action.setEnabled(can_connect)
        self._disconnect_action.setEnabled(can_disconnect)
        if self._connect_item is not None:
            self._connect_item.setEnabled_(can_connect)
        if self._disconnect_item is not None:
            self._disconnect_item.setEnabled_(can_disconnect)
