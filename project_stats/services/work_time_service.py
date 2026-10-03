from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from project_stats.models import ProjectRecord
from project_stats.runtime.idle import UNKNOWN as IDLE_UNKNOWN, IdleDetector


APP_DATA_DIR_NAME = "\u9879\u76ee\u7edf\u8ba1"
PROGRAM_DIR_NAME = "\u7a0b\u5e8f"
WORK_TIME_FILE_NAME = "work_time.json"
SCAN_INTERVAL_SECONDS = 60
MAX_CONSECUTIVE_FAILURES = 3
# 归属粒度是项目级，工作时间的版本明细不参与归属；用固定名称聚合写入，
# 保持与历史数据相同的 "versions.<名称>.days" 结构。
AGGREGATE_VERSION_NAME = "_total"
SOURCE_EXTENSIONS = {".asm", ".h", ".jz", ".mpj", ".inc", ".ash"}
IGNORED_DIR_NAMES = {
    ".git",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "obj",
    "build",
    "dist",
    "out",
    "output",
    "debug",
    "release",
}


@dataclass(slots=True, frozen=True)
class _FileStamp:
    mtime_ns: int
    size: int


@dataclass(slots=True)
class TimingSettings:
    # 开发时间统计的三个可调参数（秒）
    idle_timeout_seconds: int = 180
    active_window_seconds: int = 10 * 60
    switch_grace_seconds: int = 2 * 60


@dataclass(slots=True)
class _VersionState:
    project: ProjectRecord
    version_name: str
    version_path: Path
    baseline: dict[str, _FileStamp]
    last_change_at: float = 0.0


class WorkTimeService:
    def __init__(
        self,
        storage_path: Path | None = None,
        on_updated: Callable[[], None] | None = None,
        scan_interval_seconds: int = SCAN_INTERVAL_SECONDS,
        timing: TimingSettings | None = None,
        idle_detector: IdleDetector | None = None,
    ):
        self.storage_path = storage_path or self.default_storage_path()
        self.on_updated = on_updated
        self.scan_interval_seconds = scan_interval_seconds
        self._timing = timing or TimingSettings()
        self._idle = idle_detector or IdleDetector()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = False
        self._projects: list[ProjectRecord] = []
        self._states: dict[str, _VersionState] = {}
        self._last_scan_time: float | None = None
        self._data = self._load_data()

        # 归属状态：同一时刻最多只有一个项目在计时。
        self._owner_path: str | None = None       # 当前计时的项目路径（原始字符串）
        self._switch_at: float | None = None      # 切换观察期的起点
        self._switch_target: str | None = None    # 观察期内的候选项目
        self._pending_start: float | None = None  # 冻结时段的起点
        self._pending_seconds: float = 0.0        # 冻结中的秒数（暂不写盘）

    # ---------------------------------------------------------------- 参数

    @property
    def timing(self) -> TimingSettings:
        with self._lock:
            return TimingSettings(
                idle_timeout_seconds=self._timing.idle_timeout_seconds,
                active_window_seconds=self._timing.active_window_seconds,
                switch_grace_seconds=self._timing.switch_grace_seconds,
            )

    def configure_timing(self, timing: TimingSettings) -> None:
        # 设置界面改完立刻生效：参数只影响后续判定，已有数据不动。
        with self._lock:
            self._timing = timing

    @property
    def current_project_path(self) -> str | None:
        with self._lock:
            return self._owner_path

    @staticmethod
    def default_storage_path() -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data)
        else:
            root = Path.home() / "AppData" / "Local"
        return root / APP_DATA_DIR_NAME / WORK_TIME_FILE_NAME

    @property
    def record_path(self) -> Path:
        return self.storage_path

    def start(self) -> None:
        with self._lock:
            self._enabled = True
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._enabled = False
            self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def configure_projects(self, projects: list[ProjectRecord]) -> None:
        states: dict[str, _VersionState] = {}
        for project in projects:
            for version_name, version_path in self._discover_version_dirs(Path(project.path)):
                baseline = self._scan_source_files(version_path)
                if not baseline:
                    continue
                states[self._state_key(project.path, version_name)] = _VersionState(
                    project=project,
                    version_name=version_name,
                    version_path=version_path,
                    baseline=baseline,
                )

        with self._lock:
            self._projects = projects.copy()
            self._states = states
            self._last_scan_time = time.time()
            # 重新加载项目后，之前记的是哪台机器上的哪个目录已经无意义，重置归属。
            self._reset_attribution()

    def clear_projects(self) -> None:
        with self._lock:
            self._projects = []
            self._states = {}
            self._last_scan_time = None
            self._reset_attribution()

    def _reset_attribution(self) -> None:
        self._owner_path = None
        self._switch_at = None
        self._switch_target = None
        self._pending_start = None
        self._pending_seconds = 0.0

    def get_project_seconds(self, project_path: str) -> tuple[int, int]:
        today = datetime.now().date().isoformat()
        normalized_project_path = self._normalize_path(project_path)
        with self._lock:
            project_data = self._data.get("projects", {}).get(normalized_project_path, {})
            versions = project_data.get("versions", {})
            total_seconds = 0
            today_seconds = 0
            for version_data in versions.values():
                days = version_data.get("days", {})
                for day, seconds in days.items():
                    if not isinstance(seconds, int):
                        continue
                    total_seconds += seconds
                    if day == today:
                        today_seconds += seconds
            # 兼容按"项目"直接写入的 days（归属粒度是项目，没有版本明细）。
            for day, seconds in project_data.get("days", {}).items():
                if not isinstance(seconds, int):
                    continue
                total_seconds += seconds
                if day == today:
                    today_seconds += seconds
            return today_seconds, total_seconds

    def get_project_duration_text(self, project_path: str) -> tuple[str, str]:
        today_seconds, total_seconds = self.get_project_seconds(project_path)
        return self.format_duration(today_seconds), self.format_duration(total_seconds)

    def get_project_seconds_bulk(self, project_paths: list[str]) -> dict[str, tuple[int, int]]:
        """一次性取回多个项目的（今日, 累计）秒数，返回值以传入的路径为键。

        卡片视图要同时显示上百个项目的累计开发时间。get_project_seconds()
        单次调用就要遍历该项目全部历史 days（实测 36-57 ms），逐个项目调用会
        累积成几秒的界面卡顿；这里在同一个锁内把全部数据走一遍，并复用与
        get_project_seconds() 完全一致的口径（版本明细 + 兼容项目级 days）。
        """
        today = datetime.now().date().isoformat()
        result: dict[str, tuple[int, int]] = {path: (0, 0) for path in project_paths}
        # 存储键是 resolve + casefold 后的绝对路径。这里先用不访问文件系统的
        # abspath + normcase 建索引：151 条路径实测 0.14 ms，而 Path.resolve()
        # 要 31 ms（205 us/条，每条都要问一次文件系统）。
        key_by_normalized = {self._fast_normalize(path): path for path in project_paths}

        with self._lock:
            projects = self._data.get("projects", {})
            if not isinstance(projects, dict):
                return result

            # 快路径一条都没命中时，说明存量键的写法与 abspath+normcase 不同
            # （路径经过 junction / 符号链接，或历史数据由 resolve() 写入），
            # 这时整体按老口径重算一次索引（多花约 30 ms，且只发生一次）。
            # 不作逐条回退：没有工时记录的路径也会逐条 miss，那样反而每条都要
            # 白跑一次 resolve（151 条约 31 ms，实测确认过）。
            if projects and not (projects.keys() & key_by_normalized.keys()):
                key_by_normalized = {self._normalize_path(path): path for path in project_paths}

            for normalized_path, project_data in projects.items():
                key = key_by_normalized.get(normalized_path)
                if key is None or not isinstance(project_data, dict):
                    continue

                today_seconds = 0
                total_seconds = 0
                for version_data in project_data.get("versions", {}).values():
                    if not isinstance(version_data, dict):
                        continue
                    days = version_data.get("days", {})
                    if not isinstance(days, dict):
                        continue
                    for day, seconds in days.items():
                        if not isinstance(seconds, int):
                            continue
                        total_seconds += seconds
                        if day == today:
                            today_seconds += seconds

                # 兼容按“项目”直接写入的 days（归属粒度是项目，没有版本明细）。
                days = project_data.get("days", {})
                if isinstance(days, dict):
                    for day, seconds in days.items():
                        if not isinstance(seconds, int):
                            continue
                        total_seconds += seconds
                        if day == today:
                            today_seconds += seconds

                result[key] = (today_seconds, total_seconds)

        return result

    @staticmethod
    def format_duration(seconds: int) -> str:
        minutes = max(0, int(round(seconds / 60)))
        hours, remaining_minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}\u5c0f\u65f6{remaining_minutes:02d}\u5206"
        return f"{remaining_minutes}\u5206"

    def _run(self) -> None:
        # 这里是开发时间统计唯一的执行路径：任何未捕获异常都会让线程静默退出，
        # 之后界面一切正常、时间却再也不增长。因此必须兜住所有异常并留下日志。
        logger = logging.getLogger("project_stats.work_time")
        consecutive_failures = 0

        while not self._stop_event.wait(self.scan_interval_seconds):
            with self._lock:
                enabled = self._enabled
            if not enabled:
                continue

            try:
                updated = self.scan_once()
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception(
                    "Work-time scan failed (%s consecutive failure(s))",
                    consecutive_failures,
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    # 连续失败说明环境已经不可用（磁盘满、目录只读等）。
                    # 与其假装还在统计，不如停下并留下明确日志。
                    logger.error("Work-time tracking stopped after repeated failures")
                    with self._lock:
                        self._enabled = False
                    self._stop_event.set()
                    return
                continue

            if updated and self.on_updated is not None:
                try:
                    self.on_updated()
                except Exception:
                    logger.exception("Work-time update callback failed")

    def scan_once(self) -> bool:
        """推进一轮判定：空闲检测 → 找变化 → 归属结算。

        归属规则（同一时刻最多只有一个项目在计时）：
        - 当前项目在"无操作窗口"内，且本轮没有别的项目变化 → 时间记给当前项目；
        - 出现别的项目 B 变化 → 从此刻起冻结计时，进入观察期；
          B 在观察期内再次发生内容变化 → 确认切换，冻结时段全部记给 B；
          观察期结束 B 仍无第二次变化 → 取消切换，冻结时段归还当前项目。
        """
        now = time.time()
        idle_seconds = self._idle.get_idle_seconds()
        updated = False

        with self._lock:
            self._refresh_version_states()
            elapsed = self._elapsed_seconds(now)
            self._last_scan_time = now
            timing = self._timing

            # 1) 空闲优先：人不在电脑前，什么都不记，并停止当前项目的计时。
            if idle_seconds != IDLE_UNKNOWN and idle_seconds >= timing.idle_timeout_seconds:
                # 空闲之前已经累计的时间立即落账，不冻结、不参与切换判定。
                updated = self._settle_before_idle(now) or updated
                self._owner_path = None
                self._switch_at = None
                self._switch_target = None
                return updated

            states = list(self._states.values())
            changed_by_path: dict[str, list[_VersionState]] = {}
            for state in states:
                current = self._scan_source_files(state.version_path)
                if not current:
                    continue
                if self._has_changed(state.baseline, current):
                    state.baseline = current
                    state.last_change_at = now
                    changed_by_path.setdefault(state.project.path, []).append(state)

            owner_record = self._project_record(self._owner_path)
            inactive = elapsed > 0 and self._is_window_expired(owner_record, now, timing)
            others = [path for path in changed_by_path if path != self._owner_path]

            if elapsed > 0 and self._pending_seconds > 0:
                # 已经处于切换观察期：pending_seconds 记的是"上一轮为止"的冻结秒数，
                # 本轮 elapsed 单独结算，避免重复或漏算。
                if others:
                    # 2) 候选项目再次发生内容变化 → 确认切换。
                    target = max(others, key=lambda p: self._latest_change(p, changed_by_path))
                    updated = self._settle_forward(target, elapsed, now) or updated
                elif now >= (self._switch_at or 0.0) + timing.switch_grace_seconds:
                    # 3) 观察期结束仍无第二次变化 → 取消切换，冻结时段归还原项目。
                    updated = self._settle_back(elapsed, now) or updated
                else:
                    # 观察期内：时间继续冻结，暂不写盘。
                    self._pending_seconds += elapsed
            elif elapsed > 0 and not inactive and owner_record is not None:
                # 4) 常规计时：当前项目仍在无操作窗口内。
                if others:
                    self._start_switch(others, changed_by_path, now)
                    self._pending_seconds = elapsed
                else:
                    updated = self._record(owner_record, elapsed, now) or updated
            elif elapsed > 0 and (inactive or owner_record is None):
                # 5) 没有在计时的项目，但有项目刚发生变化 → 它成为当前项目。
                if changed_by_path:
                    newest = max(changed_by_path, key=lambda p: self._latest_change(p, changed_by_path))
                    self._claim_owner(newest, now)

            if updated:
                self._save_data()
        return updated

    # ------------------------------------------------------------ 归属辅助

    def _project_record(self, path: str | None) -> ProjectRecord | None:
        if not path:
            return None
        for state in self._states.values():
            if state.project.path == path:
                return state.project
        return None

    def _pending_target_record(self) -> ProjectRecord | None:
        # 冻结中的秒数默认归还给冻结前的项目；若已确认切换则给候选项目。
        return self._project_record(self._switch_target if self._switch_target else self._owner_path)

    @staticmethod
    def _latest_change(path: str, changed_by_path: dict[str, list[_VersionState]]) -> float:
        return max((state.last_change_at for state in changed_by_path[path]), default=0.0)

    def _is_window_expired(self, owner: ProjectRecord | None, now: float, timing: TimingSettings) -> bool:
        if owner is None:
            return True
        last_change = max(
            (state.last_change_at for state in self._states.values() if state.project.path == owner.path),
            default=0.0,
        )
        if last_change <= 0.0:
            return True
        return now - last_change > timing.active_window_seconds

    def _claim_owner(self, path: str, now: float) -> None:
        self._owner_path = path
        self._switch_at = None
        self._switch_target = None
        self._pending_start = None
        self._pending_seconds = 0.0

    def _start_switch(self, others: list[str], changed_by_path: dict[str, list[_VersionState]], now: float) -> None:
        # 发起切换的这一分钟在确认时才结算，所以 pending_seconds 从 0 起算，
        # _switch_at 记录观察期起点；确认后所有者的计时段截止到这里。
        self._switch_at = now
        self._switch_target = max(others, key=lambda p: self._latest_change(p, changed_by_path))
        self._pending_start = now
        self._pending_seconds = 0.0

    def _settle_forward(self, target_path: str, elapsed: int, now: float) -> bool:
        """确认切换：从切换时刻到现在的全部秒数记给候选项目。"""
        total = self._pending_seconds + elapsed
        self._pending_seconds = 0.0
        self._pending_start = None
        record = self._project_record(target_path)
        self._owner_path = target_path
        self._switch_at = None
        self._switch_target = None
        return self._record(record, total, now)

    def _settle_back(self, elapsed: int, now: float) -> bool:
        """取消切换：冻结时段归还给切换前的项目，并恢复它继续计时。"""
        total = self._pending_seconds + elapsed
        self._pending_seconds = 0.0
        self._pending_start = None
        self._switch_at = None
        self._switch_target = None
        return self._record(self._project_record(self._owner_path), total, now)

    def _settle_before_idle(self, now: float) -> bool:
        """空闲触发时，把当前项目【本轮之前】已累计的时间落账。

        本轮 elapsed 不计入——这一分钟人已经离开电脑，算进去就是虚高。
        """
        total = self._pending_seconds
        self._pending_seconds = 0.0
        self._pending_start = None
        return self._record(self._project_record(self._owner_path), total, now)

    def _record(self, project: ProjectRecord | None, seconds: float, now: float) -> bool:
        if project is None or seconds <= 0:
            return False
        self._record_span(project, now - seconds, now)
        return True

    def _record_span(self, project: ProjectRecord, start: float, end: float) -> None:
        # 跨零点时按午夜切开，分别写入前后两天。
        cursor = datetime.fromtimestamp(start)
        while True:
            day_end = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
            end_dt = datetime.fromtimestamp(end)
            if end_dt < day_end:
                self._add_seconds(project, cursor.date().isoformat(), int(round((end_dt - cursor).total_seconds())))
                return
            self._add_seconds(project, cursor.date().isoformat(), int(round((day_end - cursor).total_seconds())))
            cursor = day_end

    def _refresh_version_states(self) -> None:
        current_keys: set[str] = set()
        for project in self._projects:
            for version_name, version_path in self._discover_version_dirs(Path(project.path)):
                key = self._state_key(project.path, version_name)
                current_keys.add(key)
                if key in self._states:
                    self._states[key].project = project
                    self._states[key].version_path = version_path
                    continue

                baseline = self._scan_source_files(version_path)
                if not baseline:
                    continue
                self._states[key] = _VersionState(
                    project=project,
                    version_name=version_name,
                    version_path=version_path,
                    baseline=baseline,
                )

        stale_keys = [key for key in self._states if key not in current_keys]
        for key in stale_keys:
            del self._states[key]

    def _elapsed_seconds(self, now: float) -> int:
        if self._last_scan_time is None:
            return 0
        elapsed = int(now - self._last_scan_time)
        return max(0, min(elapsed, self.scan_interval_seconds))

    def _add_seconds(self, project: ProjectRecord, day: str, seconds: int) -> None:
        # 归属粒度是"项目"，而工作时间的版本明细不参与归属判定，
        # 因此统一写在一个固定的聚合项下，保持与历史数据相同的 "versions.<名称>.days" 结构，
        # 这样旧数据（按版本分桶）和新数据都能被 get_project_seconds 正确读出。
        normalized_project_path = self._normalize_path(project.path)
        projects = self._data.setdefault("projects", {})
        project_data = projects.setdefault(
            normalized_project_path,
            {
                "name": project.project_name,
                "client": project.client,
                "chip": project.chip_name,
                "package": project.package_name,
                "versions": {},
            },
        )
        project_data.update(
            {
                "name": project.project_name,
                "client": project.client,
                "chip": project.chip_name,
                "package": project.package_name,
            }
        )
        versions = project_data.setdefault("versions", {})
        aggregate = versions.setdefault(AGGREGATE_VERSION_NAME, {"path": project.path, "days": {}})
        aggregate["path"] = project.path
        days = aggregate.setdefault("days", {})
        days[day] = int(days.get(day, 0)) + int(seconds)

    def _load_data(self) -> dict:
        if not self.storage_path.exists():
            return {"schema_version": 1, "projects": {}}
        logger = logging.getLogger("project_stats.work_time")

        def quarantine(reason: str) -> None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            corrupt_path = self.storage_path.with_name(
                f"{self.storage_path.stem}.corrupt-{stamp}-{os.getpid()}{self.storage_path.suffix}"
            )
            try:
                self.storage_path.replace(corrupt_path)
                logger.error("Work-time data was invalid; moved to %s: %s", corrupt_path, reason)
            except OSError:
                logger.exception("Work-time data was invalid and could not be quarantined: %s", self.storage_path)

        try:
            raw_data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            # 损坏文件不能直接当成空数据，否则下一次保存会悄悄覆盖历史记录。
            # 先隔离原文件，保留现场供用户恢复或排查。
            quarantine(str(exc))
            return {"schema_version": 1, "projects": {}}
        if not isinstance(raw_data, dict):
            quarantine("root is not an object")
            return {"schema_version": 1, "projects": {}}
        raw_data.setdefault("schema_version", 1)
        raw_data.setdefault("projects", {})
        if not isinstance(raw_data["projects"], dict):
            quarantine("projects is not an object")
            return {"schema_version": 1, "projects": {}}
        return raw_data

    def _save_data(self) -> None:
        with self._lock:
            data = self._data
        logger = logging.getLogger("project_stats.work_time")
        # 临时文件名带上 pid，避免两个实例残留的 .tmp 互相覆盖。
        temp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.{os.getpid()}.tmp")
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.storage_path)
        except OSError:
            logger.exception("Failed to persist work time data to %s", self.storage_path)
            raise
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def _discover_version_dirs(self, project_path: Path) -> list[tuple[str, Path]]:
        program_dir = project_path / PROGRAM_DIR_NAME
        if not program_dir.is_dir():
            return []

        versions: list[tuple[str, Path]] = []
        try:
            entries = sorted(os.scandir(program_dir), key=lambda entry: entry.name)
        except OSError:
            return []

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                versions.append((entry.name, Path(entry.path)))

        if not versions and self._scan_source_files(program_dir):
            versions.append((PROGRAM_DIR_NAME, program_dir))

        return versions

    def _scan_source_files(self, root: Path) -> dict[str, _FileStamp]:
        stamps: dict[str, _FileStamp] = {}
        self._collect_source_files(root, root, stamps)
        return stamps

    def _collect_source_files(self, root: Path, current_dir: Path, stamps: dict[str, _FileStamp]) -> None:
        try:
            entries = list(os.scandir(current_dir))
        except OSError:
            return

        for entry in entries:
            name = entry.name
            if entry.is_dir(follow_symlinks=False):
                if name.lower() not in IGNORED_DIR_NAMES:
                    self._collect_source_files(root, Path(entry.path), stamps)
                continue

            if not entry.is_file(follow_symlinks=False):
                continue

            if Path(name).suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            relative_path = str(Path(entry.path).relative_to(root)).lower()
            stamps[relative_path] = _FileStamp(
                mtime_ns=stat_result.st_mtime_ns,
                size=stat_result.st_size,
            )

    @staticmethod
    def _has_changed(previous: dict[str, _FileStamp], current: dict[str, _FileStamp]) -> bool:
        return previous != current

    @staticmethod
    def _state_key(project_path: str, version_name: str) -> str:
        return f"{WorkTimeService._normalize_path(project_path)}|{version_name}"

    @staticmethod
    def _normalize_path(path: str) -> str:
        # 慢路径：会展开 junction / 符号链接 / 8.3 短名，每次都要访问文件系统。
        return str(Path(path).resolve()).casefold()

    @staticmethod
    def _fast_normalize(path: str) -> str:
        # 快路径：纯字符串运算。对普通本地路径，结果与 _normalize_path() 完全一致
        # （151 条真实路径逐条比对 0 例外），只有经过 junction / 符号链接时才会分叉。
        return os.path.normcase(os.path.abspath(path)).casefold()
