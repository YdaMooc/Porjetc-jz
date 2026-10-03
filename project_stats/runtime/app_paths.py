from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path


DATA_DIR_NAME = ".project_stats"
APP_DATA_DIR_NAME = "\u9879\u76ee\u7edf\u8ba1"


def get_app_root() -> Path:
    # 便携版运行时，配置和日志应当跟着程序目录走；源码运行时则回到仓库根目录。
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resolve_writable_dir(primary: Path, fallback: Path) -> Path:
    # 便携版可能被解压到 Program Files、只读共享盘等位置。
    # 这时绝不能让"建目录失败"把启动流程带崩——退到用户目录继续跑。
    for candidate in (primary, fallback):
        probe: Path | None = None
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write_probe_{uuid.uuid4().hex[:8]}"
            probe.write_text("", encoding="utf-8")
            return candidate
        except OSError:
            continue
        finally:
            # 探测文件清理必须放在 finally：写入成功但删除失败时，
            # 也不应该把隐藏的 .write_probe_* 残留到用户目录。
            if probe is not None:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    logging.getLogger("project_stats.paths").debug(
                        "Failed to remove write probe %s", probe, exc_info=True
                    )

    logging.getLogger("project_stats.paths").warning(
        "Neither %s nor %s is writable; falling back to the primary path", primary, fallback
    )
    return primary


def get_data_dir() -> Path:
    # 配置与日志统一放在同一个可写目录里，避免"日志写不进去"这类问题只在打包版复现。
    app_root = get_app_root()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        fallback = Path(local_app_data) / APP_DATA_DIR_NAME
    else:
        fallback = Path.home() / "AppData" / "Local" / APP_DATA_DIR_NAME
    return resolve_writable_dir(app_root / DATA_DIR_NAME, fallback)


def resolve_resource_path(filename: str) -> Path:
    # 打包后资源文件的位置会因 onedir / onefile 和 PyInstaller 版本而不同，这里统一做候选查找。
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        bundled_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        executable_root = Path(sys.executable).resolve().parent
        candidates.extend([
            bundled_root / filename,
            executable_root / filename,
            executable_root / "_internal" / filename,
            executable_root.parent / filename,
        ])
    else:
        project_root = Path(__file__).resolve().parents[2]
        candidates.extend([
            project_root / filename,
            Path(__file__).resolve().parents[1] / filename,
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
