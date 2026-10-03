"""安全打包发布脚本（v1.0.5 新增）。

解决的问题：旧的 `build.bat`（已于 2026-10-03 从仓库删除，副本在 `backups\\` 的源码快照里）
先删除 `portable\\`（含 dist）再开始构建，一旦构建失败，新旧产物会一起消失。本脚本改为：

    1. 构建到临时目录 `.release_build\\dist`，构建期间完全不碰 `portable\\`；
    2. 构建成功才替换 `portable\\dist`，失败则原样保留上一版产物；
    3. 在 `releases\\` 下生成带版本号的便携版 zip、源码快照 zip、
       SHA256SUMS.txt 与 manifest_v<版本>.json。

用法（必须用项目自带的虚拟环境）：

    .venv\\Scripts\\python.exe tools\\make_release.py            # 完整流程
    .venv\\Scripts\\python.exe tools\\make_release.py --no-build # 只重新打包现有 dist
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from project_stats.app_info import APP_BUILD_DATE, APP_NAME, APP_VERSION  # noqa: E402

STAGING_DIR = PROJECT_ROOT / ".release_build"
STAGING_DIST = STAGING_DIR / "dist"
STAGING_WORK = STAGING_DIR / "build"
PORTABLE_DIR = PROJECT_ROOT / "portable"
PORTABLE_DIST = PORTABLE_DIR / "dist"
RELEASES_DIR = PROJECT_ROOT / "releases"

# 源码快照要装进去的东西（与 backups/ 里的源码备份保持一致的口径）
SOURCE_INCLUDE_FILES = [
    ".editorconfig",
    "build.spec",
    "CHANGELOG.md",
    "README.md",
    "requirements.txt",
    "docs/版本管理.md",
    "docs/优化审查报告.md",
    "docs/开发对话总结.md",
    "项目统计.ico",
]
SOURCE_INCLUDE_DIRS = ["project_stats", "tools"]
SOURCE_SKIP_DIRS = {"__pycache__", ".venv", "releases", "portable", "backups", "mockups"}
# 打包时排除的运行期数据（程序自己会新建，不该进发布包）
ZIP_SKIP_PARTS = {"__pycache__", ".project_stats"}


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.2f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} GB"


def kill_running_app() -> None:
    """打包前结束仍在运行的旧版程序，否则替换 dist 会被文件占用挡住。"""
    subprocess.run(
        ["taskkill", "/F", "/IM", f"{APP_NAME}.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def zip_tree(source_dir: Path, zip_path: Path, arc_prefix: str) -> int:
    """把 source_dir 打进 zip，顶层套一层 arc_prefix（解压后不会散落文件）。"""
    count = 0
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(source_dir.rglob("*")):
            if not item.is_file():
                continue
            relative = item.relative_to(source_dir)
            if any(part in ZIP_SKIP_PARTS for part in relative.parts):
                continue
            archive.write(item, str(Path(arc_prefix) / relative))
            count += 1
    return count


def build_portable() -> None:
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    STAGING_DIST.mkdir(parents=True, exist_ok=True)

    spec_path = PROJECT_ROOT / "build.spec"
    log(f"开始构建 {APP_NAME} {APP_VERSION} …")
    started = time.perf_counter()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(spec_path),
            "--clean",
            "--noconfirm",
            "--distpath",
            str(STAGING_DIST),
            "--workpath",
            str(STAGING_WORK),
        ],
        cwd=str(PROJECT_ROOT),
    )
    if completed.returncode != 0:
        raise SystemExit(f"构建失败（退出码 {completed.returncode}），portable\\ 保持原样未动。")

    bundle_dir = STAGING_DIST / APP_NAME
    exe_path = bundle_dir / f"{APP_NAME}.exe"
    if not exe_path.is_file():
        raise SystemExit(f"构建结束但没找到 {exe_path}，portable\\ 保持原样未动。")
    log(f"构建完成，用时 {time.perf_counter() - started:.1f} s → {bundle_dir}")

    # 构建成功，这才替换旧产物；旧的先改名为「dist_上一版_<时间>」，便于回滚。
    # 更早的回滚产物直接清掉，避免 portable\ 下越积越多。
    for stale in sorted(PORTABLE_DIR.glob("dist_上一版_*")):
        if stale.is_dir():
            log(f"清理更早的回滚产物：{stale.name}")
            shutil.rmtree(stale, ignore_errors=True)
    kill_running_app()
    if PORTABLE_DIST.exists():
        previous = PORTABLE_DIR / f"dist_上一版_{datetime.now():%Y%m%d_%H%M%S}"
        log(f"保留上一版产物：{previous.name}")
        PORTABLE_DIST.rename(previous)
    PORTABLE_DIST.mkdir(parents=True, exist_ok=True)
    shutil.move(str(STAGING_DIST / APP_NAME), str(PORTABLE_DIST / APP_NAME))
    log(f"已替换 {PORTABLE_DIST}")


def make_source_snapshot() -> Path:
    snapshot_root = STAGING_DIR / f"{APP_NAME}_v{APP_VERSION}"
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root, ignore_errors=True)
    snapshot_root.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    for name in SOURCE_INCLUDE_FILES:
        candidate = PROJECT_ROOT / name
        if candidate.is_file():
            files.append(candidate)
    for dir_name in SOURCE_INCLUDE_DIRS:
        base = PROJECT_ROOT / dir_name
        for item in sorted(base.rglob("*")):
            if item.is_dir():
                continue
            if any(part in SOURCE_SKIP_DIRS or part == "__pycache__" for part in item.parts):
                continue
            files.append(item)

    manifest_lines = [
        f"{APP_NAME} {APP_VERSION} 源码快照",
        f"构建日期：{APP_BUILD_DATE}",
        f"打包时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"文件数：{len(files)}",
        "",
        "SHA256  大小  路径",
    ]
    for item in files:
        relative = item.relative_to(PROJECT_ROOT)
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        manifest_lines.append(f"{sha256_of(item)}  {item.stat().st_size:>9}  {relative.as_posix()}")

    (snapshot_root / "MANIFEST.txt").write_text(
        "\r\n".join(manifest_lines) + "\r\n", encoding="utf-8"
    )

    zip_path = RELEASES_DIR / f"{APP_NAME}_v{APP_VERSION}_source.zip"
    count = zip_tree(snapshot_root, zip_path, f"{APP_NAME}_v{APP_VERSION}_source")
    log(f"源码快照：{count} 个文件 → {zip_path.name}")
    return zip_path


def write_checksums() -> Path:
    lines: list[str] = []
    for item in sorted(RELEASES_DIR.glob("*")):
        if item.is_file() and item.name != "SHA256SUMS.txt":
            lines.append(f"{sha256_of(item)}  {item.name}")
    checksum_path = RELEASES_DIR / "SHA256SUMS.txt"
    checksum_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 发布打包")
    parser.add_argument("--no-build", action="store_true", help="跳过 PyInstaller，直接用现有 portable/dist 打包")
    args = parser.parse_args()

    log(f"发布 {APP_NAME} {APP_VERSION}（构建日期 {APP_BUILD_DATE}）")
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    if not args.no_build:
        build_portable()
    else:
        if not (PORTABLE_DIST / APP_NAME).is_dir():
            raise SystemExit("portable\\dist 下没有可打包的产物，去掉 --no-build 重新构建。")
        log("跳过构建，直接使用 portable\\dist")

    kill_running_app()
    bundle_dir = PORTABLE_DIST / APP_NAME
    exe_path = bundle_dir / f"{APP_NAME}.exe"
    exe_hash = sha256_of(exe_path)

    portable_zip = RELEASES_DIR / f"{APP_NAME}_v{APP_VERSION}_便携版.zip"
    file_count = zip_tree(PORTABLE_DIST, portable_zip, APP_NAME)
    log(f"便携版：{file_count} 个文件 → {portable_zip.name}")

    source_zip = make_source_snapshot()
    checksum_path = write_checksums()

    manifest = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "build_date": APP_BUILD_DATE,
        "packaged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "exe_sha256": exe_hash,
        "exe_size": exe_path.stat().st_size,
        "portable_zip": {"name": portable_zip.name, "files": file_count, "size": portable_zip.stat().st_size},
        "source_zip": {"name": source_zip.name, "size": source_zip.stat().st_size},
        "checksums": checksum_path.name,
    }
    manifest_path = RELEASES_DIR / f"manifest_v{APP_VERSION}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    shutil.rmtree(STAGING_DIR, ignore_errors=True)

    log("")
    log(f"  程序     ：{exe_path}")
    log(f"  便携版   ：{portable_zip}  ({human_size(portable_zip.stat().st_size)})")
    log(f"  源码快照 ：{source_zip}  ({human_size(source_zip.stat().st_size)})")
    log(f"  校验清单 ：{checksum_path}")
    log(f"  exe SHA256：{exe_hash}")
    log("发布完成。把 releases 里的便携版 zip 交给用户即可（解压后是「项目统计」文件夹）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
