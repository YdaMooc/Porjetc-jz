"""进程 DPI 感知与缩放系数。

必须在创建 Tk 根窗口之前调用 enable_dpi_awareness()：Windows 默认把非感知
进程的界面按系统缩放拉伸，文字会被重采样（发虚）。声明为 per-monitor 感知后
Tk 拿到真实 DPI，再由 tk scaling 把磅值换算成物理像素，中文小字才清晰。

100% 缩放下（scale == 1.0）行为与之前完全一致：像素常量不变、窗口尺寸不变。
"""

import ctypes
import logging
import sys
import tkinter as tk


logger = logging.getLogger("project_stats.dpi")
BASE_DPI = 96.0
_dpi_awareness_done = False


def enable_dpi_awareness() -> bool:
    """声明进程 DPI 感知（幂等，非 Windows 或失败时静默跳过）。"""
    global _dpi_awareness_done
    if _dpi_awareness_done:
        return True
    if sys.platform != "win32":
        _dpi_awareness_done = True
        return False

    try:
        # 1 = PROCESS_SYSTEM_DPI_AWARE，2 = PROCESS_PER_MONITOR_DPI_AWARE。
        # 取 1：多显示器混合 DPI 下 Tk 不会自动跟随窗口迁移，用系统级更稳。
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            logger.debug("DPI awareness is not available", exc_info=True)
            return False
    _dpi_awareness_done = True
    return True


def get_scale(root: tk.Misc) -> float:
    """取当前屏幕缩放系数（96 DPI = 1.0）。"""
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        return 1.0
    if dpi <= 0:
        return 1.0
    return max(1.0, round(dpi / BASE_DPI, 2))


def apply_scaling(root: tk.Misc) -> float:
    """把 Tk 的磅→像素换算对齐到真实 DPI，并返回缩放系数。"""
    scale = get_scale(root)
    try:
        root.tk.call("tk", "scaling", scale * 96.0 / 72.0)
    except tk.TclError:
        logger.debug("Failed to set tk scaling", exc_info=True)
    return scale


def scaled(value: int, scale: float) -> int:
    """把设计稿里的像素值换算成当前缩放下的像素值。"""
    return max(1, int(round(value * scale)))
