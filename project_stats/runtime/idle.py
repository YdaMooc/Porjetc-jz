"""键鼠空闲检测。

用于开发时间统计：只要用户在设定的时间内没有键盘/鼠标输入，就认为人不在电脑前，
这一段时间不计入开发时间。检测失败时返回 UNKNOWN，由调用方退化为"不做空闲判断"，
避免因为一次 API 失败就把统计完全停掉。
"""
from __future__ import annotations

import ctypes
import logging
import sys

UNKNOWN = -1.0


class _LastInputInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class IdleDetector:
    """查询"距离上一次键鼠输入过了多少秒"。

    Windows 下使用 user32!GetLastInputInfo + kernel32!GetTickCount；
    其它平台或不支持时 get_idle_seconds() 返回 UNKNOWN。
    """

    def __init__(self) -> None:
        self._user32 = None
        self._kernel32 = None
        self._info = None
        self._available = False
        self._warned = False

    @property
    def available(self) -> bool:
        if self._user32 is None:
            self._prepare()
        return self._available

    def _prepare(self) -> None:
        logger = logging.getLogger("project_stats.idle")
        if sys.platform != "win32":
            logger.info("Idle detection is only implemented on Windows; timing will not pause while away")
            self._user32 = False
            return

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
            user32.GetLastInputInfo.restype = ctypes.c_int
            kernel32.GetTickCount.restype = ctypes.c_uint32
        except OSError:
            logger.warning("Failed to load Win32 idle APIs; timing will not pause while away", exc_info=True)
            self._user32 = False
            return

        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(info)
        self._user32 = user32
        self._kernel32 = kernel32
        self._info = info
        self._available = True

    def get_idle_seconds(self) -> float:
        """返回键鼠空闲秒数；无法判断时返回 UNKNOWN。"""
        if self._user32 is None:
            self._prepare()
        if not self._available:
            return UNKNOWN

        try:
            if not self._user32.GetLastInputInfo(ctypes.byref(self._info)):
                self._warn_once("GetLastInputInfo failed")
                return UNKNOWN
            # GetTickCount 是 32 位且约 49.7 天回绕，用掩码做差可正确跨越回绕点。
            current_tick = self._kernel32.GetTickCount()
            elapsed_ms = (current_tick - self._info.dwTime) & 0xFFFFFFFF
            return elapsed_ms / 1000.0
        except OSError:
            self._warn_once("Idle query raised an OSError")
            return UNKNOWN

    def _warn_once(self, message: str) -> None:
        if self._warned:
            return
        self._warned = True
        logging.getLogger("project_stats.idle").warning("%s; treating as 'cannot tell'", message)
