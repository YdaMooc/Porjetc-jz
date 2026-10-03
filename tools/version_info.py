"""生成 Windows 可执行文件的版本资源（只在打包时由 build.spec 调用）。

背景：此前 `build.spec` 没有 `version=` 参数，exe 的「属性 → 详细信息」里
FileVersion / ProductVersion / ProductName 全是空的，用户在资源管理器里
分不清手上拿的是哪一版。版本号本身仍只在 `project_stats/app_info.py` 里
维护一份，这里只负责把它翻译成 Windows 版本资源。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    # 允许被 `python tools/version_info.py` 直接执行。
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_project_root_on_path()

from project_stats.app_info import APP_BUILD_DATE, APP_NAME, APP_VERSION  # noqa: E402


def version_quad(version: str) -> tuple[int, int, int, int]:
    """把 "1.0.5" 这类版本号补成 Windows 要求的四段数字 (1, 0, 5, 0)。"""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def build_version_info(
    app_name: str = APP_NAME,
    app_version: str = APP_VERSION,
    build_date: str = APP_BUILD_DATE,
):
    """构造 PyInstaller 的 VSVersionInfo 对象（EXE(version=...) 接受该对象）。"""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    quad = version_quad(app_version)
    version_text = ".".join(str(n) for n in quad)
    strings = [
        ("CompanyName", ""),
        ("FileDescription", f"{app_name} {app_version}"),
        ("FileVersion", version_text),
        ("InternalName", app_name),
        ("LegalCopyright", ""),
        ("OriginalFilename", f"{app_name}.exe"),
        ("ProductName", app_name),
        ("ProductVersion", app_version),
        ("Comments", f"构建日期 {build_date}"),
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=quad,
            prodvers=quad,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([StringTable("080404B0", [StringStruct(k, v) for k, v in strings])]),
            VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
        ],
    )


if __name__ == "__main__":
    info = build_version_info()
    print(f"{APP_NAME} {APP_VERSION} ({APP_BUILD_DATE}) -> {version_quad(APP_VERSION)}")
    print(info)
