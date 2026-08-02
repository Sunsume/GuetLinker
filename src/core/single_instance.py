"""Process-wide single-instance guard for GuetLinker."""

from __future__ import annotations

import ctypes
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile


class SingleInstanceGuard:
    """Hold an OS-level lock for the lifetime of one application process."""

    ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str = "GuetLinker.SingleInstance.v1") -> None:
        self.name = name
        self._handle = None
        self._kernel32 = None
        self._lock_file: QLockFile | None = None

    def acquire(self) -> bool:
        """Return ``False`` when another process already owns the lock."""
        if self._handle is not None or self._lock_file is not None:
            return True
        if os.name == "nt":
            return self._acquire_windows_mutex()
        return self._acquire_lock_file()

    def _acquire_windows_mutex(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._kernel32 = kernel32
        self._handle = handle
        return True

    def _acquire_lock_file(self) -> bool:
        safe_name = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in self.name
        )
        path = Path(tempfile.gettempdir()) / f"{safe_name}.lock"
        lock_file = QLockFile(str(path))
        lock_file.setStaleLockTime(0)
        if not lock_file.tryLock(0):
            return False
        self._lock_file = lock_file
        return True

    def release(self) -> None:
        """Release the process lock."""
        if self._handle is not None and self._kernel32 is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
            self._kernel32 = None
        if self._lock_file is not None:
            self._lock_file.unlock()
            self._lock_file = None

    def __enter__(self) -> "SingleInstanceGuard":
        if not self.acquire():
            raise RuntimeError("GuetLinker is already running")
        return self

    def __exit__(self, *_args) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass
