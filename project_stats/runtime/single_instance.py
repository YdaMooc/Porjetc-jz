from __future__ import annotations

import ctypes
import hashlib
import logging
import sys
from pathlib import Path

from project_stats.runtime.app_paths import get_app_root


ERROR_ALREADY_EXISTS = 183
SW_SHOW = 5
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


def build_mutex_name(app_root: Path | None = None) -> str:
    # 名字里带上安装路径：不同用户会话、同一台机器上的多份副本互不干扰。
    # 不用固定字符串，避免被别的进程抢注同名互斥体导致本程序永远起不来。
    root = app_root or get_app_root()
    digest = hashlib.sha1(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    return f"Local\\ProjectStats_{digest}"


class SingleInstanceManager:
    """用命名互斥体判断是否已有实例；有则把已有主窗口拉到前台。

    注意：CreateMutexW 以 bInitialOwner=False 创建，本进程**并不持有**该互斥体，
    只是把它当作一个有名字的"标记"。因此清理时只能 CloseHandle，
    不能调用 ReleaseMutex（那必然返回 ERROR_NOT_OWNER）。
    """

    def __init__(self, window_title: str, mutex_name: str | None = None):
        self.window_title = window_title
        self.mutex_name = mutex_name or build_mutex_name()
        self._kernel32 = None
        self._mutex_handle = None

    def start_or_activate_existing(self) -> bool:
        logger = logging.getLogger("project_stats.single_instance")
        if sys.platform != "win32":
            # 非 Windows 平台没有命名互斥体，退化为"不做单实例限制"，
            # 而不是在导入或启动阶段直接崩掉。
            return True

        kernel32 = self._load_kernel32()
        ctypes.set_last_error(0)
        # 返回的是 HANDLE，必须显式声明 restype，否则 ctypes 默认按 C int 处理。
        handle = kernel32.CreateMutexW(None, False, self.mutex_name)
        last_error = ctypes.get_last_error()

        if not handle:
            # 判定失败时宁可放行，也不要让程序起不来。
            logger.warning(
                "CreateMutexW failed (error=%s); continuing without single-instance guard",
                last_error,
            )
            return True

        self._mutex_handle = handle

        if last_error == ERROR_ALREADY_EXISTS:
            # 第二实例路径：句柄用完立刻释放，否则会一直留到进程结束。
            self.stop()
            self._activate_existing_window()
            return False

        return True

    def _load_kernel32(self):
        if self._kernel32 is not None:
            return self._kernel32

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
        ]
        kernel32.CloseHandle.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32 = kernel32
        return kernel32

    def _activate_existing_window(self) -> None:
        logger = logging.getLogger("project_stats.single_instance")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.ShowWindow.restype = ctypes.c_int
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        # SetWindowPos 的 hWndInsertAfter 实际是 HWND，用 c_void_p 承接才能表达 -1/-2 这类伪句柄。
        user32.SetWindowPos.restype = ctypes.c_int
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.SetForegroundWindow.restype = ctypes.c_int
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.BringWindowToTop.restype = ctypes.c_int
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]

        hwnd = user32.FindWindowW(None, self.window_title)
        if not hwnd:
            logger.info("No existing window titled %r to activate", self.window_title)
            return

        negative_one = ctypes.c_void_p(-1 & 0xFFFFFFFFFFFFFFFF)
        negative_two = ctypes.c_void_p(-2 & 0xFFFFFFFFFFFFFFFF)
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW

        # 先恢复可见，再短暂切到顶层，最后退回普通层级，通常比单纯 SetForegroundWindow 更稳。
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, negative_one, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, negative_two, 0, 0, 0, 0, flags)
        if not user32.SetForegroundWindow(hwnd):
            # 前台窗口切换受系统策略限制，失败不代表激活流程出错，仅记录。
            logger.info("SetForegroundWindow failed for hwnd=%s", hwnd)
        user32.BringWindowToTop(hwnd)

    def stop(self) -> None:
        if not self._mutex_handle:
            return

        kernel32 = self._kernel32
        handle = self._mutex_handle
        self._mutex_handle = None
        if kernel32 is None:
            return

        kernel32.CloseHandle(ctypes.c_void_p(handle))
