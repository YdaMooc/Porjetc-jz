from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw
import pystray

from project_stats.runtime.app_paths import resolve_resource_path


TRAY_SHOW_LABEL = "\u663e\u793a\u4e3b\u7a97\u53e3"
TRAY_EXIT_LABEL = "\u9000\u51fa"


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", ctypes.c_uint32 * 3),
    ]


def _load_image_file(icon_path: Path) -> Image.Image | None:
    resolved_icon_path = icon_path if icon_path.exists() else resolve_resource_path(icon_path.name)
    if not resolved_icon_path.exists():
        return None

    try:
        with Image.open(resolved_icon_path) as image:
            return image.copy()
    except OSError:
        return None


def _load_embedded_exe_icon(size: int = 64) -> Image.Image | None:
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return None

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hicon_large = ctypes.c_void_p()
    hicon_small = ctypes.c_void_p()

    shell32.ExtractIconExW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint,
    ]
    shell32.ExtractIconExW.restype = ctypes.c_uint
    user32.DestroyIcon.argtypes = [ctypes.c_void_p]
    user32.DestroyIcon.restype = ctypes.c_int

    icon_count = shell32.ExtractIconExW(
        str(Path(sys.executable)),
        0,
        ctypes.byref(hicon_large),
        ctypes.byref(hicon_small),
        1,
    )
    hicon = hicon_large.value or hicon_small.value
    if icon_count == 0 or not hicon:
        return None

    try:
        return _hicon_to_image(ctypes.c_void_p(hicon), size)
    finally:
        if hicon_large.value:
            user32.DestroyIcon(hicon_large)
        if hicon_small.value:
            user32.DestroyIcon(hicon_small)


def _hicon_to_image(hicon: ctypes.c_void_p, size: int) -> Image.Image | None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.GetDC.argtypes = [ctypes.c_void_p]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.DrawIconEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    user32.DrawIconEx.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
    gdi32.CreateDIBSection.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_BitmapInfo),
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    gdi32.CreateDIBSection.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = ctypes.c_int
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.restype = ctypes.c_int

    screen_dc = user32.GetDC(None)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap_bits = ctypes.c_void_p()
    bitmap_info = _BitmapInfo()
    bitmap_info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
    bitmap_info.bmiHeader.biWidth = size
    bitmap_info.bmiHeader.biHeight = -size
    bitmap_info.bmiHeader.biPlanes = 1
    bitmap_info.bmiHeader.biBitCount = 32
    bitmap_info.bmiHeader.biCompression = 0

    bitmap = gdi32.CreateDIBSection(
        screen_dc,
        ctypes.byref(bitmap_info),
        0,
        ctypes.byref(bitmap_bits),
        None,
        0,
    )
    if not screen_dc or not memory_dc or not bitmap or not bitmap_bits.value:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        if screen_dc:
            user32.ReleaseDC(None, screen_dc)
        return None

    previous_object = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.DrawIconEx(memory_dc, 0, 0, hicon, size, size, 0, None, 0x0003):
            return None

        raw_bytes = ctypes.string_at(bitmap_bits, size * size * 4)
        image = Image.frombuffer("RGBA", (size, size), raw_bytes, "raw", "BGRA", 0, 1)
        return image.copy()
    finally:
        if previous_object:
            gdi32.SelectObject(memory_dc, previous_object)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


def _create_fallback_image() -> Image.Image:
    # 万一没有图标资源，也要给托盘一个可识别的图标。
    # 之前的全透明位图虽然能避免流程中断，但用户会误以为托盘图标消失了。
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill="#007aff")
    draw.rounded_rectangle((13, 14, 51, 50), radius=6, fill="#ffffff")
    draw.rectangle((18, 21, 46, 25), fill="#007aff")
    draw.rectangle((18, 30, 40, 34), fill="#34c759")
    draw.rectangle((18, 39, 44, 43), fill="#ff9f0a")
    return image


class TrayService:
    def __init__(self, icon_path: Path, title: str):
        self.icon_path = icon_path
        self.title = title
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self, on_show: Callable[[], None], on_exit: Callable[[], None]) -> None:
        if self._icon is not None:
            return

        image = _load_image_file(self.icon_path) or _load_embedded_exe_icon() or _create_fallback_image()
        menu = pystray.Menu(
            # pystray 在 Windows 上是通过“默认菜单项”响应托盘图标点击的，
            # 所以“显示主窗口”要放成 default=True，而不是挂到 icon.default_action 上。
            pystray.MenuItem(TRAY_SHOW_LABEL, lambda icon, item: on_show(), default=True),
            pystray.MenuItem(TRAY_EXIT_LABEL, lambda icon, item: on_exit()),
        )
        self._icon = pystray.Icon('project_stats', image, self.title, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is None:
            return
        self._icon.stop()
        self._icon = None
        self._thread = None
