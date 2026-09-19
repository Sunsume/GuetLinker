"""Read the active input language without changing the keyboard or input source."""

from __future__ import annotations

import ctypes
import sys
from functools import lru_cache

from PySide6.QtCore import QLocale
from PySide6.QtGui import QGuiApplication


class _MacOSInputSource:
    """Text Input Source Services, including ownership of copied CF objects."""

    def __init__(self) -> None:
        self.carbon = ctypes.CDLL(
            "/System/Library/Frameworks/Carbon.framework/Carbon"
        )
        self.cf = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self.carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
        self.carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
        self.carbon.TISGetInputSourceProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p,
        ]
        self.carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        self.languages_key = ctypes.c_void_p.in_dll(
            self.carbon, "kTISPropertyInputSourceLanguages"
        )
        self.cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        self.cf.CFArrayGetCount.restype = ctypes.c_long
        self.cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        self.cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        self.cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_uint32,
        ]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.cf.CFRelease.restype = None

    def language(self) -> str | None:
        source = self.carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return None
        try:
            languages = self.carbon.TISGetInputSourceProperty(
                source, self.languages_key
            )
            if not languages or self.cf.CFArrayGetCount(languages) == 0:
                return None
            # The first BCP 47 tag describes the source's primary language.
            language = self.cf.CFArrayGetValueAtIndex(languages, 0)
            buffer = ctypes.create_string_buffer(128)
            if language and self.cf.CFStringGetCString(
                language, buffer, len(buffer), 0x08000100  # UTF-8
            ):
                return buffer.value.decode("utf-8")
            return None
        finally:
            self.cf.CFRelease(source)


@lru_cache(maxsize=1)
def _macos_input_source() -> _MacOSInputSource | None:
    try:
        return _MacOSInputSource()
    except (OSError, AttributeError, ValueError):
        return None


def is_chinese_input_active() -> bool:
    """Prefer the selected macOS input source over the system/UI language."""
    if sys.platform == "darwin":
        source = _macos_input_source()
        language = source.language() if source else None
        if language is not None:
            return language.lower().replace("_", "-").split("-")[0] == "zh"
    method = QGuiApplication.inputMethod() if QGuiApplication.instance() else None
    return bool(method and method.locale().language() == QLocale.Language.Chinese)
