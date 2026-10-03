"""进程完整性级别（Windows 强制完整性控制 MIC）检测。

程序目录里如果带着「低完整性」标签（最常见的来源：从浏览器下载后直接解压，
Windows 会给解压出来的目录打上 Low 标签），那么该目录下所有可执行文件启动的
进程都会以**低完整性**运行。低完整性进程的能力被系统限制：

  * 不能唤起资源管理器：ShellExecute 返回 ERROR_ACCESS_DENIED(5)，
    explorer.exe 直接以 0xC0000142(STATUS_DLL_INIT_FAILED) 退出。
    界面上的表现就是「打开目录 / 打开程序目录 / 双击表格打开」点了没有任何反应。
  * 不能往中等完整性的位置写文件（例如数据盘上的项目主目录），
    新建项目目录会报 [WinError 5] 拒绝访问。

这里只做只读检测，不修改任何安全描述符；修复办法见 low_integrity_hint()。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25

# 强制完整性级别：低 0x1000 / 中 0x2000 / 高 0x3000 / 系统 0x4000。
SECURITY_MANDATORY_LOW_RID = 0x1000
SECURITY_MANDATORY_MEDIUM_RID = 0x2000

# 低完整性的成因和解决办法（界面提示用，措辞按"看不懂 Win32 错误码的人"来写）。
LOW_INTEGRITY_CAUSE = (
    "程序当前以「低完整性」方式运行，Windows 不允许它调用资源管理器。\n"
    "常见原因：程序放在「下载」文件夹里（下载后直接解压），"
    "整个文件夹被系统打上了低完整性标签。"
)
LOW_INTEGRITY_FIX = (
    "解决办法：把整个程序文件夹移到桌面或其它位置后重新运行程序；"
    "如果文件夹已经在其它位置，可以对该文件夹执行一次：\n"
    "icacls \"文件夹路径\" /setintegritylevel (OI)(CI)M"
)


class _SIDAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


def current_integrity_rid() -> int | None:
    """返回当前进程完整性级别的 RID；非 Windows 或取不到时返回 None。

    取不到一律返回 None（当作"未知"），绝不抛异常：这只是诊断信息，
    不能因为它影响启动或任何功能。
    """
    if os.name != "nt":
        return None
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
        ]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)
        ):
            return None
        try:
            size = wintypes.DWORD(0)
            # 第一次调用只问需要多大缓冲区，预期返回 FALSE + ERROR_INSUFFICIENT_BUFFER。
            advapi32.GetTokenInformation(
                token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size)
            )
            if not size.value:
                return None
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi32.GetTokenInformation(
                token, TOKEN_INTEGRITY_LEVEL, buffer, size.value, ctypes.byref(size)
            ):
                return None
            label = ctypes.cast(buffer, ctypes.POINTER(_SIDAndAttributes)).contents
            if not label.Sid:
                return None
            count = advapi32.GetSidSubAuthorityCount(label.Sid).contents.value
            if not count:
                return None
            # 完整性级别编码在 SID 的最后一个子授权值里。
            return int(advapi32.GetSidSubAuthority(label.Sid, count - 1).contents.value)
        finally:
            kernel32.CloseHandle(token)
    except (OSError, AttributeError, ValueError):
        return None


def is_low_integrity() -> bool:
    """当前进程是否运行在低完整性级别（低于 Medium）。"""
    rid = current_integrity_rid()
    return rid is not None and rid < SECURITY_MANDATORY_MEDIUM_RID


def describe_integrity() -> str:
    """给日志用的一行描述，例如 "medium (0x2000)"。"""
    rid = current_integrity_rid()
    if rid is None:
        return "unknown"
    if rid < SECURITY_MANDATORY_LOW_RID:
        name = "untrusted"
    elif rid < SECURITY_MANDATORY_MEDIUM_RID:
        name = "low"
    elif rid < 0x3000:
        name = "medium"
    elif rid < 0x4000:
        name = "high"
    else:
        name = "system"
    return f"{name} (0x{rid:04X})"
