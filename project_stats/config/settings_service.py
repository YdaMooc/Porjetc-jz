import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from project_stats.runtime.app_paths import get_data_dir
from project_stats.services.project_service import DEFAULT_SEARCH_FIELDS, SEARCH_FIELD_MAP


CONFIG_FILE_NAME = "settings.json"
DEFAULT_CLOSE_ACTION = "minimize_to_background"
DEFAULT_AUTO_LOAD_LAST_PATH = True
DEFAULT_SINGLE_INSTANCE = True
DEFAULT_AUTO_TRACK_WORK_TIME = True

# 主界面视图模式：cards = 卡片墙（默认），table = 传统表格。
# 用户切换后写回配置，下次启动沿用上次选择。
VIEW_MODE_CARDS = "cards"
VIEW_MODE_TABLE = "table"
VIEW_MODES = (VIEW_MODE_CARDS, VIEW_MODE_TABLE)
DEFAULT_VIEW_MODE = VIEW_MODE_CARDS

# 开发时间统计的三个可调参数（单位：秒）
DEFAULT_IDLE_TIMEOUT_SECONDS = 180          # 键鼠空闲超过这么久，停止计时
DEFAULT_ACTIVE_WINDOW_SECONDS = 10 * 60     # 文件内容这么久没变化，停止计时
DEFAULT_SWITCH_GRACE_SECONDS = 2 * 60       # 切到别的项目后的观察期
MIN_IDLE_TIMEOUT_SECONDS = 30
MIN_ACTIVE_WINDOW_SECONDS = 60
MIN_SWITCH_GRACE_SECONDS = 30
MAX_TIMING_SECONDS = 24 * 60 * 60


@dataclass(slots=True)
class AppSettings:
    last_base_path: str = ""
    close_action: str = DEFAULT_CLOSE_ACTION
    auto_load_last_path: bool = DEFAULT_AUTO_LOAD_LAST_PATH
    single_instance: bool = DEFAULT_SINGLE_INSTANCE
    auto_track_work_time: bool = DEFAULT_AUTO_TRACK_WORK_TIME
    background_notice_shown: bool = False
    search_fields: list[str] = field(default_factory=lambda: DEFAULT_SEARCH_FIELDS.copy())
    view_mode: str = DEFAULT_VIEW_MODE
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS
    active_window_seconds: int = DEFAULT_ACTIVE_WINDOW_SECONDS
    switch_grace_seconds: int = DEFAULT_SWITCH_GRACE_SECONDS


class SettingsService:
    def __init__(self, app_root: Path | None = None):
        self.app_root = app_root
        self.config_dir = (app_root / ".project_stats") if app_root is not None else get_data_dir()
        self.config_path = self.config_dir / CONFIG_FILE_NAME

    def load(self) -> AppSettings:
        if not self.config_path.exists():
            return self.default_settings()

        try:
            raw_data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.default_settings()

        if not isinstance(raw_data, dict):
            return self.default_settings()

        close_action = self._as_str(raw_data.get("close_action"), DEFAULT_CLOSE_ACTION)
        if close_action not in {"minimize_to_background", "exit"}:
            close_action = DEFAULT_CLOSE_ACTION

        # 老配置没有 view_mode 字段，自动补默认值；非法值同样退回默认。
        view_mode = self._as_str(raw_data.get("view_mode"), DEFAULT_VIEW_MODE)
        if view_mode not in VIEW_MODES:
            view_mode = DEFAULT_VIEW_MODE

        return AppSettings(
            last_base_path=self._as_str(raw_data.get("last_base_path"), ""),
            close_action=close_action,
            auto_load_last_path=self._as_bool(raw_data.get("auto_load_last_path"), DEFAULT_AUTO_LOAD_LAST_PATH),
            single_instance=self._as_bool(raw_data.get("single_instance"), DEFAULT_SINGLE_INSTANCE),
            auto_track_work_time=self._as_bool(raw_data.get("auto_track_work_time"), DEFAULT_AUTO_TRACK_WORK_TIME),
            background_notice_shown=self._as_bool(raw_data.get("background_notice_shown"), False),
            search_fields=self._as_search_fields(raw_data.get("search_fields")),
            view_mode=view_mode,
            idle_timeout_seconds=self._as_timing(
                raw_data.get("idle_timeout_seconds"), DEFAULT_IDLE_TIMEOUT_SECONDS, MIN_IDLE_TIMEOUT_SECONDS
            ),
            active_window_seconds=self._as_timing(
                raw_data.get("active_window_seconds"), DEFAULT_ACTIVE_WINDOW_SECONDS, MIN_ACTIVE_WINDOW_SECONDS
            ),
            switch_grace_seconds=self._as_timing(
                raw_data.get("switch_grace_seconds"), DEFAULT_SWITCH_GRACE_SECONDS, MIN_SWITCH_GRACE_SECONDS
            ),
        )

    @staticmethod
    def default_settings() -> AppSettings:
        # 统一默认值入口，后面无论是首次运行还是“恢复默认”都走同一套配置。
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        # 原子写入：先写临时文件再同目录替换。直接 write_text 一旦被中断
        # （断电、任务管理器结束进程）就会留下截断的 JSON，而 load() 会静默
        # 回退到默认值，用户所有设置无声丢失。
        logger = logging.getLogger("project_stats.config")
        payload = json.dumps(asdict(settings), ensure_ascii=False, indent=2)
        temp_path = self.config_path.with_suffix(f"{self.config_path.suffix}.{os.getpid()}.tmp")
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.config_path)
        except OSError:
            # 只读安装目录不应该让程序崩溃：记录并继续，界面仍可用。
            logger.warning("Failed to save settings to %s", self.config_path, exc_info=True)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _as_str(value, default: str) -> str:
        if isinstance(value, str):
            return value
        return default

    @staticmethod
    def _as_bool(value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
        return default

    @staticmethod
    def _as_timing(value, default: int, minimum: int) -> int:
        # 计时参数容错：接受 int 或纯数字字符串，超出范围/非法一律回落默认值，
        # 避免手改配置文件写出 0 或负数导致计时逻辑退化。
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            text = value.strip()
            if not text.isdigit():
                return default
            value = int(text)
        if not isinstance(value, int):
            return default
        if value < minimum or value > MAX_TIMING_SECONDS:
            return default
        return value

    @staticmethod
    def _as_search_fields(value) -> list[str]:
        if not isinstance(value, list):
            return DEFAULT_SEARCH_FIELDS.copy()

        fields = [
            item
            for item in value
            if isinstance(item, str) and item in SEARCH_FIELD_MAP
        ]
        return fields or DEFAULT_SEARCH_FIELDS.copy()
