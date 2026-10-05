import os
import logging
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any


if __package__ in (None, ""):
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

# 说明：matplotlib / mplcursors 只在统计图窗口里用到，但它们会让启动多花约 0.6-0.9 s。
# 因此改为在 show_statistics() 内延迟导入，详见 _load_chart_modules()。

from project_stats.app_info import APP_BUILD_DATE, APP_NAME, APP_VERSION
from project_stats.models import (
    DISPLAY_CHIP_NAME,
    DISPLAY_CLIENT,
    DISPLAY_CREATED_DATE,
    DISPLAY_PACKAGE,
    DISPLAY_PROJECT_NAME,
    DISPLAY_SAMPLE_COUNT,
    DISPLAY_SALESMAN,
    DISPLAY_SEQUENCE,
    DISPLAY_WORK_TOTAL,
    DISPLAY_YEAR,
    ProjectRecord,
)
from project_stats.config import (
    AppSettings,
    SettingsService,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_ACTIVE_WINDOW_SECONDS,
    DEFAULT_SWITCH_GRACE_SECONDS,
    MIN_IDLE_TIMEOUT_SECONDS,
    MIN_ACTIVE_WINDOW_SECONDS,
    MIN_SWITCH_GRACE_SECONDS,
    MAX_TIMING_SECONDS,
    VIEW_MODE_CARDS,
    VIEW_MODE_TABLE,
    VIEW_MODES,
)
from project_stats.platform import TrayService
from project_stats.runtime import dpi
from project_stats.runtime.app_paths import get_app_root
from project_stats.runtime.integrity import (
    LOW_INTEGRITY_CAUSE,
    LOW_INTEGRITY_FIX,
    is_low_integrity,
)
from project_stats.ui import theme as ui_theme
from project_stats.ui.theme import (
    ACCENT,
    ACCENT_SOFT,
    APP_BG,
    CARD_HOVER_BG,
    CARD_HOVER_BORDER,
    CHART_GRID,
    CHART_SELECTED,
    DETAIL_BOX_BG,
    LINE,
    PANEL_BG,
    PURPLE,
    ROW_ALT,
    ROW_HOVER,
    ROW_NORMAL,
    ROW_SELECTED,
    SHADOW_COLORS,
    SHADOW_STRONG,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    WALL_BG,
    WARNING,
)
from project_stats.ui.widgets import (
    RoundedButton,
    RoundedPanel,
    SegmentedControl,
    rounded_rect_points,
)
from project_stats.services.project_service import (
    ALL_OPTION,
    DEFAULT_SEARCH_FIELDS,
    SEARCH_CLIENT,
    ProjectCatalog,
    ProjectService,
    STAT_CHIP_NAME,
    STAT_SALESMAN,
)
from project_stats.services.work_time_service import TimingSettings, WorkTimeService


# 声明 DPI 感知必须早于创建 Tk 根窗口（ProjectBrowser 在更晚才构造），
# 否则高 DPI 下文字会被系统重采样，中文小字发虚。放在导入之后是为了
# 保证 dpi 模块已经导入。
dpi.enable_dpi_awareness()


# 窗口标题带上版本号，用户一眼能看到当前用的是哪个版本（也便于排查问题时对齐）。
APP_TITLE = f"{APP_NAME} {APP_VERSION}"
# 配色、字体、像素度量统一放在 project_stats.ui.theme（见该模块顶部说明），
# 这里只保留不随 DPI / 字体变化的常量。
PATH_LABEL = "\u9879\u76ee\u4e3b\u8def\u5f84\uff1a"
BROWSE_TEXT = "\u6d4f\u89c8..."
LOAD_TEXT = "\u8bfb\u53d6\u9879\u76ee"
# 这里刻意不放 emoji：Tk 首次为 U+1F4CA 做系统字体回退匹配要 830 ms 上下
# （实测冷启动 1393 ms → 444 ms），而它只是个装饰。图标改成画布上自绘的矢量小图标。
STATS_BUTTON_TEXT = "\u9879\u76ee\u7edf\u8ba1"
YEAR_LABEL = "\u5e74\u4efd\uff1a"
SALESMAN_LABEL = "\u4e1a\u52a1\u5458\uff1a"
CLIENT_LABEL = "\u5ba2\u6237\uff1a"
CHIP_LABEL = "\u82af\u7247\u578b\u53f7\uff1a"
PACKAGE_LABEL = "\u811a\u4f4d\uff1a"
SEARCH_KEYWORD_LABEL = "\u5173\u952e\u5b57\uff1a"
CLEAR_SEARCH_TEXT = "\u6e05\u7a7a\u641c\u7d22"
CHOOSE_PATH_TITLE = "\u9009\u62e9\u4e3b\u9879\u76ee\u8def\u5f84\uff08\u4f8b\u5982 xxx\uff09"
INVALID_PATH_MESSAGE = "\u8bf7\u9009\u62e9\u6b63\u786e\u7684\u4e3b\u8def\u5f84\uff08\u4f8b\u5982 xxx\uff09"
PROMPT_TITLE = "\u63d0\u793a"
DONE_TITLE = "\u5b8c\u6210"
DONE_MESSAGE = "\u5171\u8bfb\u53d6\u5230 {count} \u4e2a\u9879\u76ee\u3002"
SUCCESS_TITLE = "\u6210\u529f"
ERROR_TITLE = "\u9519\u8bef"
STAT_WINDOW_TITLE = "\u9879\u76ee\u6570\u91cf\u7edf\u8ba1"
STAT_YEAR_LABEL = "\u9009\u62e9\u5e74\u4efd\uff1a"
STAT_TYPE_LABEL = "\u7edf\u8ba1\u7ef4\u5ea6\uff1a"
# 同 STATS_BUTTON_TEXT：emoji 首次排版要几百毫秒（Tk 要枚举系统字体找字形），
# 而统计窗口本来就要等 matplotlib，这里不再雪上加霜。
SAVE_CHART_TEXT = "\u4fdd\u5b58\u56fe\u8868"
SAVE_CHART_TITLE = "\u4fdd\u5b58\u56fe\u8868\u4e3a\u56fe\u7247"
SAVE_CHART_FILE = "\u9879\u76ee\u7edf\u8ba1_{year}.png"
SAVE_SUCCESS_MESSAGE = "\u56fe\u8868\u5df2\u4fdd\u5b58\u5230\uff1a\n{path}"
SAVE_ERROR_MESSAGE = "\u4fdd\u5b58\u5931\u8d25\uff1a{error}"
NO_DATA_MESSAGE = "{year} \u6ca1\u6709\u6570\u636e\u3002"
LOAD_FIRST_MESSAGE = "\u8bf7\u5148\u8bfb\u53d6\u9879\u76ee\u3002"
Y_AXIS_LABEL = "\u9879\u76ee\u6570\u91cf"
HOVER_TEXT = "{name}\n\u9879\u76ee\u6570: {value}"
ALL_YEARS_TEXT = "\u5168\u90e8\u5e74\u4efd"
MENU_TOOLS = "\u5de5\u5177"
MENU_ABOUT = "\u5173\u4e8e"
MENU_STATS = "\u9879\u76ee\u7edf\u8ba1"
MENU_CLEAR_SEARCH = "\u6e05\u7a7a\u641c\u7d22"
MENU_SETTINGS = "\u8bbe\u7f6e"
MENU_EXIT = "\u9000\u51fa"
ABOUT_TITLE = "\u5173\u4e8e"
ABOUT_MESSAGE = "\u9879\u76ee\u7edf\u8ba1\n\n\u529f\u80fd\uff1a\u9879\u76ee\u8bfb\u53d6\u3001\u7b5b\u9009\u3001\u5173\u952e\u5b57\u641c\u7d22\u3001\u53cc\u51fb\u6253\u5f00\u76ee\u5f55\u3001\u9879\u76ee\u7edf\u8ba1\u56fe\u8868\u3002"
SETTINGS_TITLE = "\u8bbe\u7f6e"
SETTINGS_TAB_GENERAL = "\u901a\u7528"
SETTINGS_TAB_WORK_TIME = "\u5f00\u53d1\u65f6\u95f4"
SETTINGS_TAB_SEARCH = "\u641c\u7d22\u8303\u56f4"
SETTINGS_CLOSE_LABEL = "\u5173\u95ed\u7a97\u53e3\u65f6"
SETTINGS_CLOSE_BACKGROUND = "\u9690\u85cf\u5230\u540e\u53f0"
SETTINGS_CLOSE_EXIT = "\u76f4\u63a5\u9000\u51fa"
SETTINGS_AUTO_LOAD_PATH = "\u542f\u52a8\u65f6\u6062\u590d\u4e0a\u6b21\u8def\u5f84"
SETTINGS_SINGLE_INSTANCE = "\u53ea\u5141\u8bb8\u6253\u5f00\u4e00\u4e2a\u5b9e\u4f8b"
SETTINGS_RESTART_REQUIRED = "\uff08\u4fee\u6539\u540e\u9700\u91cd\u65b0\u542f\u52a8\u7a0b\u5e8f\u751f\u6548\uff09"
SETTINGS_AUTO_TRACK_WORK_TIME = "\u81ea\u52a8\u8bb0\u5f55\u5f00\u53d1\u65f6\u95f4\uff08\u6309\u9879\u76ee\u5f52\u5c5e\uff0c\u540c\u4e00\u65f6\u523b\u53ea\u8bb0\u4e00\u4e2a\u9879\u76ee\uff09"
SETTINGS_IDLE_LABEL = "\u7a7a\u95f2\u8d85\u8fc7"
SETTINGS_ACTIVE_LABEL = "\u65e0\u64cd\u4f5c\u8d85\u8fc7"
SETTINGS_GRACE_LABEL = "\u5207\u6362\u89c2\u5bdf\u671f"
SETTINGS_SECONDS_SUFFIX = "\u79d2"
SETTINGS_IDLE_HINT = "\u952e\u76d8/\u9f20\u6807\u65e0\u8f93\u5165\u8d85\u8fc7\u8be5\u65f6\u957f \u2192 \u505c\u6b62\u8ba1\u65f6"
SETTINGS_ACTIVE_HINT = "\u6587\u4ef6\u5185\u5bb9\u65e0\u53d8\u5316\u8d85\u8fc7\u8be5\u65f6\u957f \u2192 \u505c\u6b62\u8ba1\u65f6"
SETTINGS_GRACE_HINT = "\u5207\u5230\u5176\u4ed6\u9879\u76ee\u540e\uff0c\u8fd9\u6bb5\u65f6\u95f4\u5185\u5b83\u6ca1\u518d\u53d8\u5316 \u2192 \u65f6\u95f4\u5f52\u8fd8\u539f\u9879\u76ee"
SETTINGS_TIMING_HINT = "\u63d0\u793a\uff1a\u4e09\u4e2a\u53c2\u6570\u90fd\u53ef\u8c03\uff0c\u53d6\u503c\u8303\u56f4 30 ~ 86400 \u79d2\uff1b\u4fee\u6539\u540e\u7acb\u5373\u751f\u6548\u3002"
SETTINGS_TIMING_INVALID = "\u8ba1\u65f6\u53c2\u6570\u5fc5\u987b\u662f\u6574\u6570\uff0c\u4e14\u5728 {minimum} ~ {maximum} \u79d2\u4e4b\u95f4\u3002"
SETTINGS_WORK_TIME_PATH_LABEL = "\u8bb0\u5f55\u6587\u4ef6\uff1a{path}"
SETTINGS_SEARCH_FIELDS_LABEL = "\u641c\u7d22\u8303\u56f4\uff1a"
SETTINGS_SEARCH_FIELDS_HINT = "\u52fe\u9009\u540e\uff0c\u4e3b\u754c\u9762\u7684\u5173\u952e\u5b57\u641c\u7d22\u4f1a\u5728\u8fd9\u4e9b\u5b57\u6bb5\u91cc\u67e5\u627e\u3002"
SETTINGS_SEARCH_FIELDS_REQUIRED = "\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u641c\u7d22\u8303\u56f4\u3002"
SETTINGS_SAVE_TEXT = "\u4fdd\u5b58"
SETTINGS_CANCEL_TEXT = "\u53d6\u6d88"
SETTINGS_RESET_TEXT = "\u6062\u590d\u9ed8\u8ba4"
# (标签, 说明, 设置字段名, 默认值, 最小值) —— 设置界面与校验共用同一份定义
SETTINGS_TIMING_SPECS = (
    (SETTINGS_IDLE_LABEL, SETTINGS_IDLE_HINT, "idle_timeout_seconds",
     DEFAULT_IDLE_TIMEOUT_SECONDS, MIN_IDLE_TIMEOUT_SECONDS),
    (SETTINGS_ACTIVE_LABEL, SETTINGS_ACTIVE_HINT, "active_window_seconds",
     DEFAULT_ACTIVE_WINDOW_SECONDS, MIN_ACTIVE_WINDOW_SECONDS),
    (SETTINGS_GRACE_LABEL, SETTINGS_GRACE_HINT, "switch_grace_seconds",
     DEFAULT_SWITCH_GRACE_SECONDS, MIN_SWITCH_GRACE_SECONDS),
)
NEW_PROJECT_TEXT = "\u65b0\u589e\u9879\u76ee"
DETAIL_TITLE = "\u9879\u76ee\u8be6\u60c5"
DETAIL_EMPTY = "\u5728\u5de6\u4fa7\u5217\u8868\u91cc\u9009\u4e2d\u4e00\u4e2a\u9879\u76ee\u67e5\u770b\u8be6\u60c5\u3002"
DETAIL_OPEN_DIR = "\u6253\u5f00\u76ee\u5f55"
DETAIL_COPY_PATH = "\u590d\u5236\u8def\u5f84"
DETAIL_OPEN_PROGRAM = "\u6253\u5f00\u7a0b\u5e8f\u76ee\u5f55"
DETAIL_PATH_LABEL = "\u5b8c\u6574\u8def\u5f84"
DETAIL_WORK_TIME = "\u5f00\u53d1\u65f6\u95f4"
DETAIL_WORK_TODAY = "\u4eca\u65e5"
DETAIL_WORK_TOTAL = "\u7d2f\u8ba1"
DETAIL_SAMPLE_TIMES = "{count} \u6b21"
COPY_PATH_DONE = "\u8def\u5f84\u5df2\u590d\u5236\u5230\u526a\u8d34\u677f\u3002"
COPY_PATH_FAILED = "\u590d\u5236\u5931\u8d25\uff1a{error}"
PROGRAM_DIR_MISSING = "\u8be5\u9879\u76ee\u4e0b\u6ca1\u6709\u300c\u7a0b\u5e8f\u300d\u76ee\u5f55\u3002"
SUMMARY_PROJECTS = "\u9879\u76ee"
SUMMARY_SAMPLES = "\u9001\u6837"
SUMMARY_SALESMEN = "\u4e1a\u52a1\u5458"
SUMMARY_CHIPS = "\u82af\u7247"
SUMMARY_HINT = "\u7edf\u8ba1\u8303\u56f4\uff1a\u5f53\u524d\u5217\u8868\u7b5b\u9009\u7ed3\u679c"
# 新增项目对话框
NEW_PROJECT_TITLE = "\u65b0\u589e\u9879\u76ee"
NEW_PROJECT_BASE_LABEL = "\u4e3b\u76ee\u5f55"
NEW_PROJECT_SALESMAN_LABEL = "\u4e1a\u52a1\u5458"
NEW_PROJECT_SEQUENCE_LABEL = "\u5e8f\u53f7"
NEW_PROJECT_CLIENT_LABEL = "\u5ba2\u6237\u7f16\u53f7"
NEW_PROJECT_DATE_LABEL = "\u7acb\u9879\u65e5\u671f"
NEW_PROJECT_NAME_LABEL = "\u9879\u76ee\u540d\u79f0"
NEW_PROJECT_PREVIEW_LABEL = "\u5c06\u521b\u5efa\u7684\u9879\u76ee\u76ee\u5f55"
NEW_PROJECT_SEQUENCE_HINT = "\u6309\u5f53\u5e74\u8be5\u4e1a\u52a1\u5458\u9879\u76ee\u6570\u81ea\u52a8\u751f\u6210\uff08\u4e0d\u53ef\u4fee\u6539\uff09"
NEW_PROJECT_DATE_HINT = "\u51b3\u5b9a\u653e\u5728\u54ea\u4e2a\u5e74\u4efd\u76ee\u5f55\u4e0b"
NEW_PROJECT_NAME_HINT = "\u53ef\u4ee5\u5305\u542b\u8fde\u5b57\u7b26"
NEW_PROJECT_NAME_CALIBRATE_HINT = "\u4e5f\u53ef\u7c98\u8d34\u201c\u4e1a\u52a1\u5458-\u5ba2\u6237\u7f16\u53f7-\u9879\u76ee\u540d-\u65e5\u671f\u201d\uff0c\u7cfb\u7edf\u4f1a\u81ea\u52a8\u6821\u51c6\u524d\u9762\u5b57\u6bb5"
NEW_PROJECT_CREATE_TEXT = "\u521b\u5efa"
NEW_PROJECT_REQUIRED = "\u8bf7\u586b\u5199\u4e1a\u52a1\u5458\u3001\u5ba2\u6237\u7f16\u53f7\u3001\u9879\u76ee\u540d\u79f0\u548c\u7acb\u9879\u65e5\u671f\u3002"
NEW_PROJECT_BAD_DATE = "\u7acb\u9879\u65e5\u671f\u683c\u5f0f\u5e94\u4e3a YYYY-MM-DD\uff0c\u4e14\u5fc5\u987b\u662f\u6709\u6548\u65e5\u671f\u3002"
NEW_PROJECT_EXISTS = "\u76ee\u5f55\u5df2\u5b58\u5728\uff1a{path}"
NEW_PROJECT_FAILED = "\u521b\u5efa\u5931\u8d25\uff1a{error}"
NEW_PROJECT_OK = "\u5df2\u521b\u5efa\uff1a\n{path}"
NEW_PROJECT_ASK_LOAD = "\u662f\u5426\u7acb\u5373\u8bfb\u53d6\u9879\u76ee\uff0c\u4ee5\u4fbf\u5728\u5217\u8868\u91cc\u770b\u5230\u5b83\uff1f"
NEW_PROJECT_CONFIRM = "\u5c06\u5728\u4ee5\u4e0b\u4f4d\u7f6e\u521b\u5efa\u9879\u76ee\u76ee\u5f55\uff1a\n\n{path}\n\n\u786e\u8ba4\u521b\u5efa\uff1f"
NEW_PROJECT_INVALID_NAME = "\u9879\u76ee\u540d\u79f0\u4e0d\u80fd\u5305\u542b \\ / : * ? \" < > | \u8fd9\u4e9b\u5b57\u7b26\u3002"
NEW_PROJECT_INVALID_SALESMAN = "\u4e1a\u52a1\u5458\u540d\u79f0\u4e0d\u80fd\u5305\u542b \\ / : * ? \" < > | \u8fd9\u4e9b\u5b57\u7b26\u3002"
BACKGROUND_NOTICE = "\u7a0b\u5e8f\u5df2\u9690\u85cf\u5230\u7cfb\u7edf\u6258\u76d8\uff0c\u53ef\u4ee5\u53cc\u51fb\u6258\u76d8\u56fe\u6807\u6216\u901a\u8fc7\u6258\u76d8\u83dc\u5355\u6062\u590d\u7a97\u53e3\u3002"
OPEN_MISSING_MESSAGE = "\u9879\u76ee\u76ee\u5f55\u5df2\u4e0d\u5b58\u5728\uff08\u53ef\u80fd\u5df2\u88ab\u91cd\u547d\u540d\u3001\u79fb\u52a8\u6216\u5220\u9664\uff09\uff0c\u8bf7\u91cd\u65b0\u8bfb\u53d6\u9879\u76ee\u3002"
OPEN_FAILED_MESSAGE = "\u65e0\u6cd5\u6253\u5f00\u76ee\u5f55\uff1a{error}"
# 低完整性进程调用资源管理器会被系统直接拒绝（ShellExecute 报 5，
# explorer.exe 以 0xC0000142 退出），必须把原因和处理办法说清楚，否则就是"点了没反应"。
OPEN_BLOCKED_LOW_INTEGRITY = (
    "无法打开文件夹。\n\n"
    f"{LOW_INTEGRITY_CAUSE}\n\n"
    f"{LOW_INTEGRITY_FIX}"
)
NEW_PROJECT_LOW_INTEGRITY_HINT = f"\n\n{LOW_INTEGRITY_CAUSE}\n\n{LOW_INTEGRITY_FIX}"
NONE_FOUND_MESSAGE = "\u672a\u8bfb\u5230\u4efb\u4f55\u9879\u76ee\uff1a\u8be5\u76ee\u5f55\u4e0b\u6ca1\u6709\u300c\u5e74\u4efd/\u4e1a\u52a1\u5458/\u9879\u76ee\u76ee\u5f55\u300d\u8fd9\u79cd\u7ed3\u6784\uff0c\u8bf7\u786e\u8ba4\u4e3b\u8def\u5f84\u662f\u5426\u9009\u5bf9\u3002"
EMPTY_TABLE_TEXT = "\u6682\u65e0\u9879\u76ee\n\u8bf7\u5148\u8bfb\u53d6\u4e00\u4e2a\u4e3b\u8def\u5f84"
EMPTY_FILTER_TEXT = "\u6ca1\u6709\u5339\u914d\u7684\u9879\u76ee\n\u53ef\u5c1d\u8bd5\u6e05\u7a7a\u7b5b\u9009\u6761\u4ef6"
LOADING_TABLE_TEXT = "\u6b63\u5728\u8bfb\u53d6\u9879\u76ee\u2026"
LOAD_TIMEOUT_MS = 15_000
LOAD_TIMEOUT_TEXT = "读取超时：目录可能位于不可访问的网络盘，请重新选择本地项目目录"
DEFAULT_CLOSE_ACTION = "minimize_to_background"
EXIT_CLOSE_ACTION = "exit"
APP_ICON_FILE = "\u9879\u76ee\u7edf\u8ba1.ico"

# ---------------------------------------------------------------- 卡片视图（方案 E）
# 主界面有两种呈现方式，共用同一套筛选 / 搜索 / 详情数据：
#   cards = 卡片墙（默认，自适应分栏 + 卡片内展开详情）
#   table = 传统表格（保留原有的 9 列 Treeview 与右栏详情）
VIEW_LABEL_CARDS = "\u5361\u7247\u89c6\u56fe"
VIEW_LABEL_TABLE = "\u8868\u683c\u89c6\u56fe"
SORT_LABEL = "\u6392\u5e8f\uff1a"
SORT_RECENT = "\u6700\u8fd1\u7acb\u9879"
SORT_OPTIONS = (SORT_RECENT, DISPLAY_PROJECT_NAME, DISPLAY_SAMPLE_COUNT, DISPLAY_WORK_TOTAL)
MENU_TOGGLE_VIEW = "\u5207\u6362\u5230 \u5361\u7247 / \u8868\u683c \u89c6\u56fe"
STATUS_SUMMARY = ("\u9879\u76ee {projects} \u00b7 \u9001\u6837 {samples} \u00b7 "
                  "\u4e1a\u52a1\u5458 {salesmen} \u00b7 \u82af\u7247 {chips}")
CARD_SAMPLE_LABEL = "\u9001\u6837"
CARD_WORK_LABEL = "\u7d2f\u8ba1"
# 字段名用全角空格补齐到 4 个字宽，四行数值就能自然对齐（CJK 字宽 = 全角空格宽）。
CARD_FIELD_PAD = "\u3000"
CARD_FIELD_LABEL_WIDTH = 4
EMPTY_VALUE = "\u2014"
CARD_META_SEPARATOR = " \u00b7 "
CARD_MAX_COLUMNS = 4          # 一屏最多几列（再宽也保持 4 列，避免卡片过宽）
MOUSE_WHEEL_UNIT = 120
CARD_LAYOUT_MAX_RETRIES = 8      # 窗口尚未布局完成时的重排重试次数
# 卡片墙用画布绘制：一张卡 = 阴影几层圆角面 + 卡面圆角 + 3 段文字。
# 控件版（Frame + 3 个 Label）在 151 个项目上实测首次建墙约 1.1 s（Tk 逐控件测文字），
# 同样的内容画到画布上只要几十毫秒，所以这里走画布。
CARD_ELLIPSIS = "\u2026"
CARD_PATH_PREFIX = "\u2026\\"     # 卡内路径按“相对主路径”显示，前面加个省略号提示


class ProjectBrowser(tk.Tk):
    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        # 主题必须最先建立：tk scaling 要先对齐真实 DPI，字体才能量准，
        # 后面的卡片度量、画布圆角半径都从 theme 取。
        self._scale = dpi.apply_scaling(self)
        self.theme = ui_theme.create_theme(self, self._scale)
        self.title(APP_TITLE)
        window_width, window_height = self.theme.window_size
        self.geometry(f"{window_width}x{window_height}")
        min_width, min_height = self.theme.window_min
        self.minsize(min_width, min_height)
        self.resizable(True, True)

        self.project_service = ProjectService()
        self.settings_service = SettingsService()
        # 允许调用方复用已读到的配置（启动阶段为了判断单实例已经读过一次），避免重复读盘。
        self.settings = settings if settings is not None else self.settings_service.load()
        self.work_time_service = WorkTimeService(on_updated=self.request_work_time_refresh)
        self.tray_service = TrayService(get_app_root() / APP_ICON_FILE, APP_TITLE)
        self.all_projects: list[ProjectRecord] = []
        self.year_list: list[str] = []
        self.sales_list: list[str] = []
        self.client_list: list[str] = []
        self.chip_list: list[str] = []
        self.package_list: list[str] = []
        self._search_after_id: str | None = None
        self._load_in_progress = False
        self._load_token = 0
        self._load_timeout_id: str | None = None
        self._column_widths: dict[str, int] = {}
        self._item_paths: dict[str, str] = {}
        self._path_to_item: dict[str, str] = {}
        self._projects_by_path: dict[str, ProjectRecord] = {}
        self._selected_path: str | None = None
        self._suspend_selection_event = False
        self._last_tree_width = 0
        self._last_fit_width = 0        # 上次参与列宽计算的可用宽度（用于去重）
        self._refit_after_id: str | None = None
        # 详情面板里的开发时间（字段值放在 detail_vars 里，随表格一同维护）
        self.detail_today_var = tk.StringVar(value="—")
        self.detail_total_var = tk.StringVar(value="—")
        # 卡片视图状态：_view_mode 决定起始形态（沿用上次选择）；
        # 卡片墙把整墙画在画布上，_card_layout 是当前卡片数据（含图元 id）。
        self._view_mode = self.settings.view_mode if self.settings.view_mode in VIEW_MODES else VIEW_MODE_CARDS
        self._filtered_projects: list[ProjectRecord] = []
        # 卡片墙状态：_card_layout 是当前屏幕上的卡片数据（含画布图元 id）
        self._card_layout: list[dict[str, Any]] = []
        self._card_index: dict[str, dict[str, Any]] = {}
        self._hover_card: dict[str, Any] | None = None
        self._card_columns = 0
        self._card_cell_width = 0
        self._card_detail_frame: ttk.Frame | None = None
        self._card_detail_window: int | None = None
        self._card_detail_owner: str | None = None
        self._card_detail_index: int | None = None
        self._card_detail_height = self.theme.card_detail_min
        self._card_relayout_after_id: str | None = None
        self._card_layout_retries = 0
        # 主题里的命名字体本身就是 Font 对象，直接用（改字体只需改 theme）
        self._card_title_font = self.theme.card_title
        self._card_text_font = self.theme.card_body
        # 字段区固定四行，详情区就接在它下面
        self._card_fields_height = self._card_text_font.metrics("linespace") * 4
        self.summary_inline_var = tk.StringVar(value="")
        self._tray_show_requested = threading.Event()
        self._tray_exit_requested = threading.Event()
        self.is_background_hidden = False
        self.status_var = tk.StringVar(value="就绪")
        self.logger = logging.getLogger("project_stats.ui")

        self._apply_ui_style()
        self._build_menu()
        self._build_widgets()
        # 起始视图必须在控件建好之后确定：卡片视图要把右栏收起来。
        self._apply_view_mode(refresh=False)
        self._apply_settings()
        self._register_tray_request_handler()
        self.protocol("WM_DELETE_WINDOW", self.handle_close)

    def report_callback_exception(self, exc, val, tb) -> None:
        # Tk 的回调异常默认只会打印到控制台；这里把它落到日志里，再给用户一个更干净的错误提示。
        self.logger.exception("Unhandled Tk callback exception", exc_info=(exc, val, tb))
        try:
            messagebox.showerror(ERROR_TITLE, str(val))
        except tk.TclError:
            pass

    def _apply_ui_style(self) -> None:
        # 具体样式集中在 project_stats.ui.theme，这里只负责应用（含 ttk 主题切换）。
        self.configure(background=APP_BG)
        ui_theme.apply_ttk_theme(self, self.theme)

    def _register_tray_request_handler(self) -> None:
        self.after(200, self._poll_tray_requests)

    def _poll_tray_requests(self) -> None:
        if self._tray_show_requested.is_set():
            self._tray_show_requested.clear()
            self.activate_main_window()

        if self._tray_exit_requested.is_set():
            self._tray_exit_requested.clear()
            self.exit_application()

        self.after(200, self._poll_tray_requests)

    def _build_menu(self) -> None:
        # 菜单也尽量贴近浅色系统菜单，避免和主界面脱节。
        menu_bar = tk.Menu(
            self,
            tearoff=False,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=ACCENT_SOFT,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            relief="flat",
        )

        tools_menu = tk.Menu(
            menu_bar,
            tearoff=False,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=ACCENT_SOFT,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            relief="flat",
        )
        tools_menu.add_command(label=MENU_STATS, command=self.show_statistics)
        tools_menu.add_command(label=MENU_CLEAR_SEARCH, command=self.clear_search)
        tools_menu.add_command(label=MENU_TOGGLE_VIEW, command=self.toggle_view_mode)
        tools_menu.add_command(label=MENU_SETTINGS, command=self.show_settings)
        tools_menu.add_separator()
        tools_menu.add_command(label=MENU_EXIT, command=self.exit_application)
        menu_bar.add_cascade(label=MENU_TOOLS, menu=tools_menu)

        about_menu = tk.Menu(
            menu_bar,
            tearoff=False,
            bg=PANEL_BG,
            fg=TEXT_PRIMARY,
            activebackground=ACCENT_SOFT,
            activeforeground=TEXT_PRIMARY,
            bd=0,
            relief="flat",
        )
        about_menu.add_command(label=MENU_ABOUT, command=self.show_about)
        menu_bar.add_cascade(label=MENU_ABOUT, menu=about_menu)

        self.config(menu=menu_bar)

    def _build_widgets(self) -> None:
        # 结构（卡片视图 = 方案 E；表格视图沿用 D2 布局）：
        #   行0：主路径 + [卡片视图｜表格视图] + 主操作
        #   行1：概览指标（项目 / 送样 / 业务员 / 芯片）
        #   行2：筛选 + 搜索 + 列表；表格视图右侧为当前项目详情
        #   行3：状态栏
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        # ---------------- 行 0：主路径 + 视图切换 + 操作按钮
        frame_path = ttk.Frame(self, style="Band.TFrame", padding=(12, 12, 12, 8))
        frame_path.grid(row=0, column=0, sticky="ew")
        # 路径框吃掉剩余宽度，按钮固定在右侧，避免窗口变化时相互重叠
        frame_path.columnconfigure(0, weight=1)

        self.path_var = tk.StringVar()
        self.entry_path = ttk.Entry(frame_path, textvariable=self.path_var)
        self.entry_path.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self._build_view_switch(frame_path)

        # 工具栏按钮自绘圆角（见 ui/widgets.RoundedButton）；
        # 它同样接受 configure(state="disabled")，加载期间禁用逻辑不用改。
        gap = dpi.scaled(8, self._scale)
        self.btn_browse = RoundedButton(frame_path, self.theme, BROWSE_TEXT, command=self.choose_path, kind="soft")
        self.btn_browse.grid(row=0, column=2, padx=(0, gap))
        self.btn_load = RoundedButton(frame_path, self.theme, LOAD_TEXT, command=self.load_projects, kind="primary")
        self.btn_load.grid(row=0, column=3, padx=(0, gap))
        self.btn_new_project = RoundedButton(frame_path, self.theme, NEW_PROJECT_TEXT, command=self.show_new_project, kind="soft")
        self.btn_new_project.grid(row=0, column=4, padx=(0, gap))
        self.btn_stats = RoundedButton(frame_path, self.theme, STATS_BUTTON_TEXT, command=self.show_statistics,
                                       kind="primary", icon="chart")
        self.btn_stats.grid(row=0, column=5, padx=(0, gap))
        self.btn_settings_top = RoundedButton(frame_path, self.theme, SETTINGS_TITLE, command=self.show_settings, kind="soft")
        self.btn_settings_top.grid(row=0, column=6)

        # 键盘入口：Ctrl+1 / Ctrl+2 直接切视图，Ctrl+Tab 轮流切。
        self.bind("<Control-Key-1>", lambda _event: self.set_view_mode(VIEW_MODE_CARDS))
        self.bind("<Control-Key-2>", lambda _event: self.set_view_mode(VIEW_MODE_TABLE))
        self.bind("<Control-Key-k>", lambda _event: self._focus_search())

        # ---------------- 行 1：概览指标
        # summary_vars 在右侧详情构建时初始化，因此先建侧栏模型，再把指标渲染到顶部。

        # ---------------- 行 1：左右两栏
        content = ttk.Frame(self, style="Band.TFrame", padding=(12, 0, 12, 6))
        content.grid(row=2, column=0, sticky="nsew")
        # 详情栏保持信息可读，但把更多空间留给项目列表。
        content.columnconfigure(0, weight=68, minsize=540)
        content.columnconfigure(1, minsize=14)
        content.columnconfigure(2, weight=32, minsize=300)
        content.rowconfigure(0, weight=1)
        self._content_frame = content

        left = ttk.Frame(content, style="Band.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)      # 只有列表纵向伸展
        self._left_column = left

        # 左栏第 1 行：五个筛选
        frame_filter = ttk.Frame(left, style="Band.TFrame")
        frame_filter.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        filter_specs = (
            # 过滤器的宽度保持紧凑，让右侧信息卡在宽窗口下也能获得
            # 设计稿中的约 40% 空间；实际文本仍会通过下拉框滚动查看。
            (YEAR_LABEL, "year_var", "combo_year", 5),
            (SALESMAN_LABEL, "sales_var", "combo_sales", 7),
            (CLIENT_LABEL, "client_var", "combo_client", 7),
            (CHIP_LABEL, "chip_var", "combo_chip", 8),
            (PACKAGE_LABEL, "package_var", "combo_package", 6),
        )
        for index, (label, var_name, combo_name, width) in enumerate(filter_specs):
            column = index * 2
            ttk.Label(frame_filter, text=label, style="Band.TLabel", font=self.theme.ui).grid(
                row=0, column=column, sticky="w"
            )
            var = tk.StringVar()
            setattr(self, var_name, var)
            combo = ttk.Combobox(frame_filter, textvariable=var, state="readonly", width=width)
            combo.grid(row=0, column=column + 1, sticky="w", padx=(2, 5))
            combo.bind("<<ComboboxSelected>>", lambda e: self.update_table())
            setattr(self, combo_name, combo)

        # 左栏第 2 行：关键字搜索
        frame_search = ttk.Frame(left, style="Band.TFrame")
        frame_search.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        frame_search.columnconfigure(1, weight=1)

        ttk.Label(frame_search, text=SEARCH_KEYWORD_LABEL, style="Band.TLabel", font=self.theme.ui).grid(
            row=0, column=0, sticky="w"
        )
        self.search_keyword_var = tk.StringVar()
        self.entry_search_keyword = ttk.Entry(frame_search, textvariable=self.search_keyword_var)
        self.entry_search_keyword.grid(row=0, column=1, sticky="ew", padx=(4, 10))
        # 搜索框输入会频繁触发，这里用短延迟合并刷新，避免每敲一个字就重绘整表。
        self.entry_search_keyword.bind("<KeyRelease>", lambda e: self.schedule_table_refresh())
        self.btn_clear_search = ttk.Button(
            frame_search, text=CLEAR_SEARCH_TEXT, command=self.clear_search, style="CompactSoft.TButton"
        )
        self.btn_clear_search.grid(row=0, column=2, sticky="w")
        self.search_keyword_var.trace_add("write", lambda *_: self._update_search_controls())
        self._update_search_controls()

        # 左栏第 3 行：列表。表格与卡片墙占同一格，按当前视图模式二选一显示。
        self._build_table(left)
        self._build_card_wall(left)

        # 右栏：信息卡 + 详情（表格视图专用；卡片视图下详情在卡片内部展开）
        self._build_side_panel(content)
        self._build_overview_strip()

        # ---------------- 状态栏
        status_frame = ttk.Frame(self, style="Band.TFrame", padding=(12, 6, 12, 10))
        status_frame.grid(row=3, column=0, sticky="ew")
        ttk.Separator(status_frame, style="Card.TSeparator").pack(fill="x", pady=(0, 6))
        status_row = ttk.Frame(status_frame, style="Band.TFrame")
        status_row.pack(fill="x")
        # 卡片视图没有右栏信息卡，统计数字补到状态栏右侧（表格视图下这段文字为空）。
        # 注意：必须先 pack 右侧这块，再 pack 会 expand 的状态文字，否则前者拿不到宽度。
        self.summary_inline_label = ttk.Label(
            status_row, textvariable=self.summary_inline_var, style="Status.TLabel", anchor="e"
        )
        self.summary_inline_label.pack(side="right", padx=(10, 0))
        ttk.Label(status_row, textvariable=self.status_var, style="Status.TLabel", anchor="w").pack(
            side="left", fill="x", expand=True
        )

    def _focus_search(self) -> str:
        """快速搜索入口，保持 Ctrl+K 在两种视图下都可用。"""
        self.entry_search_keyword.focus_set()
        self.entry_search_keyword.selection_range(0, tk.END)
        return "break"

    def _build_overview_strip(self) -> None:
        """顶部概览指标：让用户在不打开统计窗口的情况下先读懂当前数据规模。"""
        panel = RoundedPanel(
            self, self.theme, fill=PANEL_BG,
            padding=(dpi.scaled(16, self._scale), dpi.scaled(8, self._scale)),
            hug=True,
        )
        panel.grid(row=1, column=0, sticky="ew", padx=dpi.scaled(12, self._scale), pady=(0, dpi.scaled(8, self._scale)))
        body = panel.body
        body.columnconfigure(0, weight=0)
        body.columnconfigure(5, weight=1)
        ttk.Label(body, text="概览", style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 18))
        metrics = (
            (SUMMARY_PROJECTS, ACCENT),
            (SUMMARY_SAMPLES, SUCCESS),
            (SUMMARY_SALESMEN, WARNING),
            (SUMMARY_CHIPS, PURPLE),
        )
        for index, (label, color) in enumerate(metrics, start=1):
            body.columnconfigure(index, weight=0, uniform="overview")
            cell = ttk.Frame(body, style="Metric.TFrame")
            cell.grid(row=0, column=index, sticky="ew", padx=(0 if index == 1 else 18, 18))
            ttk.Label(cell, text=label, style="MetricLabel.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=self.summary_vars[label], style="MetricValue.TLabel",
                      foreground=color).pack(anchor="w", pady=(1, 0))
        ttk.Label(body, text="Ctrl+K  快速搜索", style="Status.TLabel", anchor="e").grid(
            row=0, column=5, sticky="e"
        )

    def _build_table(self, parent: ttk.Frame) -> None:
        # Treeview 自己画不出圆角，所以整块表格放进圆角面板；内容内缩一点，
        # 圆角才不会被方角的表格盖掉。
        inset = dpi.scaled(5, self._scale)
        panel = RoundedPanel(parent, self.theme, fill=PANEL_BG, padding=(inset, inset))
        panel.grid(row=2, column=0, sticky="nsew")
        self._table_frame = panel
        frame_table = panel.body

        # 列表只放能一眼扫完的字段；完整路径、开发时间等放在右侧详情里。
        self.columns = (
            DISPLAY_SEQUENCE,
            DISPLAY_YEAR,
            DISPLAY_SALESMAN,
            DISPLAY_CLIENT,
            DISPLAY_PROJECT_NAME,
            DISPLAY_CHIP_NAME,
            DISPLAY_PACKAGE,
            DISPLAY_CREATED_DATE,
            DISPLAY_SAMPLE_COUNT,
        )
        self.tree = ttk.Treeview(
            frame_table,
            columns=self.columns,
            show="headings",
            height=10,
            style="Project.Treeview",
            selectmode="browse",
        )

        # 数字列居中，文字列左对齐，减少“表格看起来整齐但读起来费劲”的问题。
        text_columns = {
            DISPLAY_SALESMAN,
            DISPLAY_CLIENT,
            DISPLAY_PROJECT_NAME,
            DISPLAY_CHIP_NAME,
        }
        center_columns = set(self.columns) - text_columns
        column_anchors = {
            column: ("w" if column in text_columns else "center")
            for column in center_columns | text_columns
        }

        # 预留一个 hover 标签，鼠标移动时只改变当前行，不触碰选中状态。
        self._hover_item: str | None = None
        self._header_press = False
        self._tree_text_columns = text_columns
        self._tree_column_anchors = column_anchors

        # 初始列宽只作占位；真实宽度由 _fit_columns_to_width 按可用空间分配。
        # 这里刻意取最小值，避免 Treeview 的请求宽度把整个窗口撑到比屏幕还宽。
        default_widths = {
            DISPLAY_SEQUENCE: 34,
            DISPLAY_YEAR: 40,
            DISPLAY_SALESMAN: 54,
            DISPLAY_CLIENT: 54,
            DISPLAY_PROJECT_NAME: 80,
            DISPLAY_CHIP_NAME: 60,
            DISPLAY_PACKAGE: 44,
            DISPLAY_CREATED_DATE: 60,
            DISPLAY_SAMPLE_COUNT: 36,
        }
        # 表头采用列表专用短文案，避免紧凑列宽下被截断；详情卡片仍使用完整字段名。
        heading_labels = {
            DISPLAY_SEQUENCE: "#",
            DISPLAY_SAMPLE_COUNT: "送样",
        }
        self._heading_labels = {col: heading_labels.get(col, col) for col in self.columns}
        self._heading_font = tkfont.Font(self, font=self.theme.ui_bold)
        for col in self.columns:
            self.tree.heading(col, text=self._heading_labels[col])
            self.tree.column(col, width=default_widths[col], anchor=column_anchors[col], stretch=False)
        self.tree.configure(cursor="arrow")

        # 列宽不主导窗口尺寸，否则 Treeview 的请求宽度会把窗口顶到比屏幕还宽；
        # 实际宽度在 <Configure> 里按可用空间分配（见 _fit_columns_to_width）。
        self.tree["displaycolumns"] = self.columns

        # 只保留纵向滚动条：列宽是按可用宽度自适应分配的（见 _fit_columns_to_width），
        # 横向永远装得下，常驻一条横向滚动条只会白占高度、也和设计稿不一致。
        yscroll = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview,
                                style="Project.Vertical.TScrollbar")
        self.xscroll = ttk.Scrollbar(frame_table, orient="horizontal", command=self.tree.xview,
                                     style="Horizontal.TScrollbar")
        self._horizontal_scroll_visible = False
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=self.xscroll.set)
        yscroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.empty_state_label = ttk.Label(frame_table, text=EMPTY_TABLE_TEXT, style="EmptyState.TLabel",
                                           anchor="center", justify="center")
        self.empty_state_label.place(relx=0.5, rely=0.52, anchor="center")
        self.tree.bind("<Double-1>", self.open_selected_project)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selection)
        self.tree.bind("<Configure>", self._on_tree_configure)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda _event: self._set_hover_item(None))
        # Treeview 默认允许拖动表头分隔线；列表列宽由程序统一计算，禁止手动改列宽。
        self.tree.bind("<ButtonPress-1>", self._on_tree_button_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_tree_button_drag, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_button_release, add="+")

        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("even", background=ROW_NORMAL)
        self.tree.tag_configure("hover", background=ROW_HOVER)

        # 常用动作不必依赖鼠标：读取、聚焦搜索、清空搜索都提供键盘入口。
        self.bind("<F5>", lambda _event: self.load_projects())
        self.bind("<Control-l>", lambda _event: self.entry_search_keyword.focus_set())
        self.bind("<Escape>", lambda _event: self.clear_search())

    def _on_tree_configure(self, event) -> None:
        if abs(event.width - self._last_tree_width) < 4:
            return
        self._last_tree_width = event.width
        self._fit_columns_to_width()
        self._schedule_column_refit()

    def _on_tree_motion(self, event) -> None:
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.tree.selection():
            item_id = None
        self._set_hover_item(item_id or None)

    def _on_tree_button_press(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region in {"heading", "separator"}:
            self._header_press = True
            return "break"
        self._header_press = False
        return None

    def _on_tree_button_drag(self, _event):
        if self._header_press:
            return "break"
        return None

    def _on_tree_button_release(self, _event):
        if self._header_press:
            self._header_press = False
            return "break"
        return None

    def _set_hover_item(self, item_id: str | None) -> None:
        if item_id == self._hover_item:
            return
        if self._hover_item:
            try:
                tags = tuple(tag for tag in self.tree.item(self._hover_item, "tags") if tag != "hover")
                self.tree.item(self._hover_item, tags=tags)
            except tk.TclError:
                pass
        self._hover_item = item_id
        if item_id:
            try:
                tags = tuple(tag for tag in self.tree.item(item_id, "tags") if tag != "hover")
                self.tree.item(item_id, tags=tags + ("hover",))
            except tk.TclError:
                self._hover_item = None

    def _fit_columns_to_width(self) -> None:
        """按 Treeview 的当前宽度重新分配列宽：长文本列（项目名称）优先获得空间。

        用控件当前宽度而不是事件里的宽度，并预留出纵向滚动条与边框，
        否则最后一列会被挤出可视区、出现横向滚动条。
        """
        available = self.tree.winfo_width()
        if available <= 1:                      # 还没完成首次布局
            available = self._last_tree_width
        # 宽度没变就直接返回：载入数据时这条路径会被调用 3-4 次，其中约一半完全重复
        # （稳态每次 4-5 ms，首帧期间每次可达 33 ms）；宽度不变时下面的副作用
        # （横向滚动条显隐、_apply_column_widths）都是幂等的。
        if available == self._last_fit_width and self._column_widths:
            return
        self._last_fit_width = available
        # Treeview 已经在纵向滚动条旁边独立布局，winfo_width() 不包含滚动条宽度；
        # 这里只预留控件自身的少量边框，避免右侧出现一整段未被列填充的空白。
        chrome = 4
        usable = max(300, available - chrome)
        weights = {
            DISPLAY_SEQUENCE: 0.4,
            DISPLAY_YEAR: 0.6,
            DISPLAY_SALESMAN: 1.0,
            DISPLAY_CLIENT: 1.1,
            DISPLAY_PROJECT_NAME: 3.6,
            DISPLAY_CHIP_NAME: 1.6,
            DISPLAY_PACKAGE: 0.8,
            DISPLAY_CREATED_DATE: 1.2,
            DISPLAY_SAMPLE_COUNT: 0.6,
        }
        # 最小列宽按真实字体测量：不同字体/DPI 下同一个值的像素宽度差很多，
        # 硬编码数字在换字体后会把 "K00123456" 截成 "K0012345("。
        # 下面这些只用来量宽度，刻意用匿名占位值，不放真实业务数据。
        samples = {
            DISPLAY_SEQUENCE: "888",
            DISPLAY_YEAR: "2026",
            DISPLAY_SALESMAN: "业务员甲",
            DISPLAY_CLIENT: "K00123456",
            DISPLAY_PROJECT_NAME: "项目名称示例",
            DISPLAY_CHIP_NAME: "型号A00000000",
            DISPLAY_PACKAGE: "TSSOP20",
            DISPLAY_CREATED_DATE: "2026-09-23",
            DISPLAY_SAMPLE_COUNT: "888",
        }
        cell_pad = dpi.scaled(12, self._scale)          # 单元格左右内边距 + 一点余量
        minimums = {
            column: max(
                self.theme.ui.measure(samples[column]),
                self._heading_font.measure(self._heading_labels[column]),   # 表头也不能被切
            ) + cell_pad
            for column in self.columns
        }
        minimums[DISPLAY_PROJECT_NAME] = max(minimums[DISPLAY_PROJECT_NAME], dpi.scaled(150, self._scale))
        total_weight = sum(weights.values())
        widths: dict[str, int] = {}
        for column in self.columns:
            share = int(usable * weights[column] / total_weight)
            widths[column] = max(minimums[column], share)

        # 宽度受最小值抬高的部分从最宽的列里扣回来，确保总和不超过可用宽度，
        # 否则会出现横向滚动条、最右一列被挤出可视区。
        overflow = sum(widths.values()) - usable
        if overflow > 0:
            for column in sorted(self.columns, key=lambda c: -widths[c]):
                if overflow <= 0:
                    break
                room = widths[column] - minimums[column]
                if room <= 0:
                    continue
                take = min(room, overflow)
                widths[column] -= take
                overflow -= take
        # 如果窗口确实太窄，保留表头最小宽度并显示横向滚动条，
        # 不再按比例压缩导致文字被切掉。
        total = sum(widths.values())
        if total > usable:
            self._set_horizontal_scrollbar(True)
        else:
            self._set_horizontal_scrollbar(False)

        self._column_widths = widths
        self._apply_column_widths()

    def _set_horizontal_scrollbar(self, visible: bool) -> None:
        if visible == self._horizontal_scroll_visible:
            return
        self._horizontal_scroll_visible = visible
        if visible:
            self.xscroll.pack(side="bottom", fill="x")
        else:
            self.xscroll.pack_forget()
        # pack 改变 Treeview 宽度后再计算一次，避免首轮布局留下多余空白。
        try:
            self.after_idle(self._fit_columns_to_width)
        except (tk.TclError, RuntimeError):
            pass

    def _schedule_column_refit(self) -> None:
        # 首次布局时控件宽度还会变化，等一切稳定后再按最终宽度重算一次。
        if self._refit_after_id is not None:
            try:
                self.after_cancel(self._refit_after_id)
            except (tk.TclError, ValueError):
                pass
        self._refit_after_id = self.after(120, self._refit_columns)

    def _refit_columns(self) -> None:
        self._refit_after_id = None
        self._fit_columns_to_width()

    def _build_side_panel(self, parent: ttk.Frame) -> None:
        side = ttk.Frame(parent, style="Band.TFrame")
        side.grid(row=0, column=2, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(0, weight=1)
        self._side_panel = side

        # 顶部概览条复用这些变量；详情侧栏不再重复显示同一组数字。
        self.summary_vars: dict[str, tk.StringVar] = {
            label: tk.StringVar(value="—")
            for label in (SUMMARY_PROJECTS, SUMMARY_SAMPLES, SUMMARY_SALESMEN, SUMMARY_CHIPS)
        }

        # 项目详情：同样是圆角 + 阴影；内部靠浅分隔线和浅色信息块分层，
        # 避免“白卡片套白卡片”导致文字与背景对比失衡。
        detail_panel = RoundedPanel(
            side, self.theme, fill=PANEL_BG,
            padding=(dpi.scaled(12, self._scale), dpi.scaled(11, self._scale)),
        )
        detail_panel.grid(row=0, column=0, sticky="nsew")
        detail = detail_panel.body
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(2, weight=1)

        ttk.Label(detail, text=DETAIL_TITLE, style="DetailSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(detail, style="Detail.TSeparator").grid(row=1, column=0, sticky="ew", pady=(8, 10))

        body = ttk.Frame(detail, style="Detail.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        fields = ttk.Frame(body, style="Detail.TFrame")
        fields.grid(row=0, column=0, sticky="new")
        fields.columnconfigure(0, minsize=54)
        fields.columnconfigure(1, weight=1)
        fields.columnconfigure(2, minsize=54)
        fields.columnconfigure(3, weight=1)
        self.detail_vars = {
            key: tk.StringVar(value="—")
            for key in ("project_name", "salesman", "client", "chip_name",
                        "package_name", "created_date", "sample_count", "path")
        }
        field_specs = (
            (DISPLAY_PROJECT_NAME, "project_name"),
            (DISPLAY_SALESMAN, "salesman"),
            (SEARCH_CLIENT, "client"),
            (DISPLAY_CHIP_NAME, "chip_name"),
            (DISPLAY_PACKAGE, "package_name"),
            (DISPLAY_CREATED_DATE, "created_date"),
            (DISPLAY_SAMPLE_COUNT, "sample_count"),
        )
        for index, (label, key) in enumerate(field_specs):
            row = (index // 2) * 2
            column = (index % 2) * 2
            ttk.Label(fields, text=label, style="Detail.TLabel").grid(
                row=row, column=column, sticky="w", pady=(0, 2)
            )
            ttk.Label(fields, textvariable=self.detail_vars[key], style="DetailValue.TLabel",
                      wraplength=150, justify="left").grid(
                row=row, column=column + 1, sticky="w", padx=(7, 8), pady=(0, 2)
            )
            if index == 1 or index == 3 or index == 5:
                ttk.Separator(fields, style="Detail.TSeparator").grid(
                    row=row + 1, column=0, columnspan=4, sticky="ew", pady=0
                )

        time_frame = ttk.Frame(body, style="Detail.TFrame")
        time_frame.grid(row=1, column=0, sticky="ew", pady=(9, 0))
        time_frame.columnconfigure(0, weight=1)
        ttk.Label(time_frame, text=DETAIL_WORK_TIME, style="DetailSection.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Separator(time_frame, style="Detail.TSeparator").grid(row=1, column=0, sticky="ew", pady=(5, 6))

        work_box = ttk.Frame(time_frame, style="WorkTime.TFrame", padding=(8, 4))
        work_box.grid(row=2, column=0, sticky="ew")
        work_box.columnconfigure(1, weight=1)
        ttk.Label(work_box, text=DETAIL_WORK_TODAY, style="WorkTimeLabel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(work_box, textvariable=self.detail_today_var, style="WorkTimeToday.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(work_box, text=DETAIL_WORK_TOTAL, style="WorkTimeLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(work_box, textvariable=self.detail_total_var, style="WorkTimeTotal.TLabel").grid(
            row=1, column=1, sticky="e", pady=(2, 0)
        )

        path_box = ttk.Frame(time_frame, style="DetailPath.TFrame", padding=(8, 5))
        path_box.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        path_box.columnconfigure(0, weight=1)
        ttk.Label(path_box, text=DETAIL_PATH_LABEL, style="DetailPathLabel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(path_box, textvariable=self.detail_vars["path"], style="DetailPathValue.TLabel",
                  wraplength=320, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = ttk.Frame(detail, style="Detail.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.btn_open_dir = ttk.Button(actions, text=DETAIL_OPEN_DIR, command=self.open_selected_project,
                                       style="CompactPrimary.TButton")
        self.btn_open_dir.pack(side="left", padx=(0, 5))
        self.btn_copy_path = ttk.Button(actions, text=DETAIL_COPY_PATH, command=self.copy_selected_path,
                                        style="CompactSoft.TButton")
        self.btn_copy_path.pack(side="left", padx=(0, 5))
        self.btn_open_program = ttk.Button(actions, text=DETAIL_OPEN_PROGRAM, command=self.open_selected_program_dir,
                                           style="CompactSoft.TButton")
        self.btn_open_program.pack(side="left")

    # ============================================================ 卡片视图（方案 E）

    def _build_view_switch(self, parent: ttk.Frame) -> None:
        """工具栏里的视图切换按钮与卡片排序下拉。"""
        bar = ttk.Frame(parent, style="Band.TFrame")
        bar.grid(row=0, column=1)

        self.view_switch = SegmentedControl(
            bar, self.theme, (VIEW_LABEL_CARDS, VIEW_LABEL_TABLE),
            command=self._on_view_switch,
            active=0 if self._view_mode == VIEW_MODE_CARDS else 1,
        )
        self.view_switch.pack(side="left")

        # 排序只对卡片墙有意义（表格靠列对齐阅读），所以只在卡片视图里显示。
        self.sort_var = tk.StringVar(value=SORT_RECENT)
        self.sort_label = ttk.Label(bar, text=SORT_LABEL, style="Band.TLabel", font=self.theme.ui)
        self.sort_combo = ttk.Combobox(
            bar, textvariable=self.sort_var, state="readonly", width=10, values=list(SORT_OPTIONS)
        )
        self.sort_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_sort_changed())

    def _on_view_switch(self, index: int) -> None:
        self.set_view_mode(VIEW_MODE_CARDS if index == 0 else VIEW_MODE_TABLE)

    def set_view_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES or mode == self._view_mode:
            return
        self._view_mode = mode
        self.settings.view_mode = mode
        self._save_settings()
        self._apply_view_mode()

    def toggle_view_mode(self) -> None:
        self.set_view_mode(VIEW_MODE_TABLE if self._view_mode == VIEW_MODE_CARDS else VIEW_MODE_CARDS)

    def _apply_view_mode(self, refresh: bool = True) -> None:
        """按当前视图模式切换布局：卡片视图把右栏让给卡片墙。"""
        cards = self._view_mode == VIEW_MODE_CARDS

        if cards:
            self._side_panel.grid_remove()
            self._content_frame.columnconfigure(1, minsize=0)
            self._content_frame.columnconfigure(2, weight=0, minsize=0)
            self._table_frame.grid_remove()
            self._card_frame.grid()
            self.sort_label.pack(side="left", padx=(10, 0))
            self.sort_combo.pack(side="left", padx=(4, 0))
        else:
            self._card_frame.grid_remove()
            self._table_frame.grid()
            self._side_panel.grid()
            self._content_frame.columnconfigure(1, minsize=14)
            self._content_frame.columnconfigure(2, weight=32, minsize=300)
            self.sort_label.pack_forget()
            self.sort_combo.pack_forget()

        self.view_switch.set_active(0 if cards else 1)

        if not refresh:
            return
        if cards:
            # 表格内容在卡片视图里不再维护，清掉旧行，避免遗留的 tree 选中影响“打开目录”。
            self._clear_table_rows()
            self._rebuild_cards(self._filtered_projects)
        else:
            self.update_table()

    def _build_card_wall(self, parent: ttk.Frame) -> None:
        """卡片墙：整墙直接画在一张 Canvas 上（实测数据见文件顶部的 CARD_* 说明）。

        墙面用比卡片略深的底色（WALL_BG），卡片再用圆角 + 阴影"浮"起来；
        外圈同样套一层圆角面板，和表格视图的观感保持一致。
        """
        inset = dpi.scaled(4, self._scale)
        panel = RoundedPanel(parent, self.theme, fill=WALL_BG, padding=(inset, inset))
        panel.grid(row=2, column=0, sticky="nsew")
        self._card_frame = panel

        frame = panel.body
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self._card_canvas = tk.Canvas(
            frame, background=WALL_BG, highlightthickness=0, bd=0, takefocus=0, cursor="arrow"
        )
        self._card_scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self._card_canvas.yview, style="Project.Vertical.TScrollbar"
        )
        self._card_canvas.configure(yscrollcommand=self._card_scroll.set)
        self._card_scroll.pack(side="right", fill="y")
        self._card_canvas.pack(side="left", fill="both", expand=True)

        self._card_canvas.bind("<Configure>", self._on_card_canvas_configure)
        self._card_canvas.bind("<MouseWheel>", self._on_card_mousewheel)
        self._card_canvas.bind("<Motion>", self._on_card_motion)
        self._card_canvas.bind("<Leave>", lambda _event: self._set_hover_card(None))
        self._card_canvas.bind("<Button-1>", self._on_card_click)
        self._card_canvas.bind("<Double-Button-1>", self._on_card_double_click)

        self.card_empty_label = tk.Label(
            frame, text=EMPTY_TABLE_TEXT, background=WALL_BG, foreground=TEXT_TERTIARY,
            font=self.theme.ui, anchor="center", justify="center",
        )

    # ---------------------------------------------------------- 卡片数据与绘制

    def _rebuild_cards(self, projects: list[ProjectRecord]) -> None:
        """按当前筛选结果重建卡片数据并整墙重画（151 张卡实测约 50 ms）。"""
        if not hasattr(self, "_card_canvas"):
            return

        seconds_map = (
            self.work_time_service.get_project_seconds_bulk([p.path for p in projects]) if projects else {}
        )
        ordered = self._sort_projects(projects, seconds_map)

        self._collapse_card_detail(redraw=False)
        self._card_layout = []
        self._card_index = {}
        self._hover_card = None
        for index, project in enumerate(ordered):
            card: dict[str, Any] = {
                "index": index,
                "path": project.path,
                "project": project,
                "seconds": seconds_map.get(project.path, (0, 0)),
                "selected": project.path == self._selected_path,
                "hover": False,
                "rect": None, "shadow": [], "title": None, "meta": None, "fields": None,
                "x": 0, "y": 0, "w": 0, "h": self.theme.card_height,
            }
            self._card_layout.append(card)
            self._card_index[project.path] = card

        self._update_card_empty_state(bool(self._card_layout))
        self._draw_cards(self._card_canvas.winfo_width())

    def _draw_cards(self, width: int) -> None:
        """整墙重画：算分栏与每行 y，然后重建全部画布图元。"""
        self._card_relayout_after_id = None
        canvas = self._card_canvas
        if not self._card_layout:
            canvas.delete("card")
            canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        content_width = width if width > 1 else canvas.winfo_width()
        if content_width <= 1:
            # 数据可能比窗口映射更早回来，这时量不到宽度；稍后重试几次，
            # 之后 canvas 的 <Configure> 还会再触发一次，不会一直空着。
            if self._card_layout_retries < CARD_LAYOUT_MAX_RETRIES:
                self._card_layout_retries += 1
                self._card_relayout_after_id = self.after(80, lambda: self._draw_cards(0))
            return
        self._card_layout_retries = 0

        usable = max(self.theme.card_min_width, content_width - self.theme.card_gap)
        columns = max(1, min(CARD_MAX_COLUMNS, int((usable + self.theme.card_gap) // (self.theme.card_min_width + self.theme.card_gap))))
        cell_width = max(self.theme.card_min_width, (content_width - self.theme.card_gap) // columns) - self.theme.card_gap
        # 卡片本体要比格子窄一圈（阴影边距），文字宽度再扣掉卡片内边距。
        wrap_width = max(120, cell_width - 2 * (self.theme.shadow_pad + self.theme.card_pad))
        self._card_columns = columns
        self._card_cell_width = cell_width

        # 逐行算 y：展开的那一行比其它行高出一块详情区。
        rows = (len(self._card_layout) + columns - 1) // columns
        row_y: list[int] = []
        y = self.theme.card_gap // 2 + self.theme.shadow_pad      # 首行也要给阴影留出空间
        for row in range(rows):
            row_y.append(y)
            first, last = row * columns, min((row + 1) * columns, len(self._card_layout))
            expanded_in_row = self._card_detail_index is not None and first <= self._card_detail_index < last
            y += self.theme.card_height + (self._card_detail_height if expanded_in_row else 0) + self.theme.card_gap

        canvas.delete("card")
        for index, card in enumerate(self._card_layout):
            row, column = divmod(index, columns)
            x = self.theme.card_gap // 2 + column * (cell_width + self.theme.card_gap)
            top = row_y[row]
            # 展开的那张卡把边框一直画到详情区底部，详情看起来就在卡内。
            height = self.theme.card_height + (self._card_detail_height if index == self._card_detail_index else 0)
            card["x"], card["y"], card["w"], card["h"] = x, top, cell_width, height

            # 卡片本体四周留出阴影边距：先画阴影（几层向下偏移的圆角面），再画卡面。
            pad = self.theme.shadow_pad
            left, right = x + pad, x + cell_width - pad
            upper, lower = top + pad, top + height - pad
            fill, outline = self._card_colors(card)
            card["shadow"] = self._draw_card_shadow(left, upper, right, lower)
            card["rect"] = canvas.create_polygon(
                rounded_rect_points(left, upper, right, lower, self.theme.radius_card),
                smooth=True, splinesteps=14, fill=fill, outline=outline, width=1, tags="card",
            )
            text_x = left + self.theme.card_pad
            title_top = upper + self.theme.card_pad
            card["title"] = canvas.create_text(
                text_x, title_top, text=self._fit_card_title(self._card_title_text(card), wrap_width),
                anchor="nw", font=self._card_title_font, fill=TEXT_PRIMARY, justify="left", tags="card",
            )
            card["meta"] = canvas.create_text(
                text_x, title_top + self.theme.card_title_block, text=self._card_meta_text(card["project"]),
                anchor="nw", font=self._card_text_font, fill=TEXT_SECONDARY, tags="card",
            )
            card["fields"] = canvas.create_text(
                text_x, title_top + self.theme.card_title_block + self.theme.card_meta_block,
                text=self._card_fields_text(card["project"], card["seconds"]),
                anchor="nw", font=self._card_text_font, fill=TEXT_PRIMARY, justify="left", tags="card",
            )

        canvas.configure(scrollregion=(0, 0, content_width, y))
        self._place_card_detail()

    def _shadow_layers(self) -> tuple[tuple[int, int, str], ...]:
        """阴影分层：(向下偏移, 左右外扩, 颜色)，由近到远、由深到浅，模拟羽化。"""
        scale = self._scale
        return (
            (dpi.scaled(3, scale), dpi.scaled(1, scale), SHADOW_COLORS[0]),
            (dpi.scaled(2, scale), 0, SHADOW_COLORS[1]),
            (dpi.scaled(1, scale), 0, SHADOW_COLORS[2]),
        )

    def _draw_card_shadow(self, left: int, upper: int, right: int, lower: int) -> list[int]:
        canvas = self._card_canvas
        radius = self.theme.radius_card
        items = []
        for offset, spread, color in self._shadow_layers():
            items.append(canvas.create_polygon(
                rounded_rect_points(left - spread, upper + offset, right + spread, lower + offset, radius),
                smooth=True, splinesteps=14, fill=color, outline=color, tags="card",
            ))
        return items

    def _place_card_detail(self) -> None:
        """把展开的详情控件摆到对应卡片的字段区下方（卡片已经为它留了高度）。"""
        if self._card_detail_window is None or self._card_detail_index is None:
            return
        if self._card_detail_index >= len(self._card_layout):
            return
        card = self._card_layout[self._card_detail_index]
        canvas = self._card_canvas
        inset = self.theme.shadow_pad + self.theme.card_pad
        canvas.coords(
            self._card_detail_window,
            card["x"] + inset,
            card["y"] + self.theme.card_height - self.theme.card_pad + dpi.scaled(6, self._scale),
        )
        canvas.itemconfigure(self._card_detail_window, width=max(120, card["w"] - 2 * inset))
        canvas.tag_raise(self._card_detail_window)

    @staticmethod
    def _card_title_text(card: dict[str, Any]) -> str:
        project: ProjectRecord = card["project"]
        return project.project_name or project.full_project_name

    @staticmethod
    def _card_colors(card: dict[str, Any]) -> tuple[str, str]:
        if card["selected"]:
            return ROW_SELECTED, ACCENT
        if card["hover"]:
            return CARD_HOVER_BG, CARD_HOVER_BORDER
        return PANEL_BG, LINE

    def _repaint_card(self, card: dict[str, Any]) -> None:
        if card["rect"] is None:
            return
        canvas = self._card_canvas
        fill, outline = self._card_colors(card)
        canvas.itemconfigure(card["rect"], fill=fill, outline=outline)
        # 悬停/选中时阴影加深一点，卡片有"浮起来"的感觉。
        colors = SHADOW_STRONG if (card["hover"] or card["selected"]) else SHADOW_COLORS
        for item, color in zip(card.get("shadow") or (), colors):
            canvas.itemconfigure(item, fill=color, outline=color)

    def _fit_card_title(self, text: str, width: int) -> str:
        """标题限制在两行以内，放不下就用省略号收尾（完整项目全称在展开的详情里）。"""
        font = self._card_title_font
        if font.measure(text) <= width:
            return text
        first = ""
        rest = text
        while rest and font.measure(first + rest[0]) <= width:
            first += rest[0]
            rest = rest[1:]
        second = ""
        while rest and font.measure(second + rest[0]) <= width:
            second += rest[0]
            rest = rest[1:]
        if rest:
            while second and font.measure(second + CARD_ELLIPSIS) > width:
                second = second[:-1]
            second += CARD_ELLIPSIS
        return f"{first}\n{second}" if second else first

    @staticmethod
    def _card_meta_text(project: ProjectRecord) -> str:
        parts = [project.year, project.salesman, project.client]
        return CARD_META_SEPARATOR.join(part for part in parts if part) or EMPTY_VALUE

    def _card_fields_text(self, project: ProjectRecord, seconds: tuple[int, int]) -> str:
        _, total_seconds = seconds
        lines = (
            f"{self._card_field_label(DISPLAY_CHIP_NAME)}{project.chip_name or EMPTY_VALUE}",
            f"{self._card_field_label(DISPLAY_PACKAGE)}{project.package_name or EMPTY_VALUE}",
            f"{self._card_field_label(CARD_SAMPLE_LABEL)}"
            f"{DETAIL_SAMPLE_TIMES.format(count=project.sample_count)}",
            f"{self._card_field_label(CARD_WORK_LABEL)}"
            f"{self.work_time_service.format_duration(total_seconds)}",
        )
        return "\n".join(lines)

    @staticmethod
    def _card_field_label(text: str) -> str:
        # 用全角空格把字段名补到等宽，四行数值就能自然对齐。
        return text + CARD_FIELD_PAD * max(0, CARD_FIELD_LABEL_WIDTH - len(text))

    def _sort_projects(
        self, projects: list[ProjectRecord], seconds_map: dict[str, tuple[int, int]]
    ) -> list[ProjectRecord]:
        mode = self.sort_var.get()
        if mode == DISPLAY_PROJECT_NAME:
            return sorted(projects, key=lambda item: (item.project_name or item.full_project_name).casefold())
        if mode == DISPLAY_SAMPLE_COUNT:
            return sorted(projects, key=lambda item: -item.sample_count)
        if mode == DISPLAY_WORK_TOTAL:
            return sorted(projects, key=lambda item: -seconds_map.get(item.path, (0, 0))[1])
        # 默认「最近立项」：created_date 是 YYYY-MM-DD，按字符串倒序即时间倒序。
        return sorted(projects, key=lambda item: (item.created_date, item.year, item.sequence), reverse=True)

    def _on_card_canvas_configure(self, event) -> None:
        # 拖动窗口会连续触发 Configure，合并成一次延迟重排。
        if self._card_relayout_after_id is not None:
            self.after_cancel(self._card_relayout_after_id)
        width = event.width
        self._card_relayout_after_id = self.after(120, lambda: self._draw_cards(width))

    def _on_card_mousewheel(self, event) -> str:
        steps = int(event.delta / MOUSE_WHEEL_UNIT)
        if steps == 0:
            steps = 1 if event.delta > 0 else -1
        first, last = self._card_canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return "break"          # 内容全部可见，不做无意义的滚动
        self._card_canvas.yview_scroll(-steps, "units")
        if event.widget is self._card_canvas:
            # 滚动后光标下的卡片可能变了，顺手把悬停态跟上。
            self._set_hover_card(self._card_at(event.x, event.y))
        return "break"

    def _update_card_empty_state(self, has_cards: bool) -> None:
        if has_cards or self._load_in_progress:
            self.card_empty_label.place_forget()
            return
        self.card_empty_label.configure(text=EMPTY_FILTER_TEXT if self.all_projects else EMPTY_TABLE_TEXT)
        self.card_empty_label.place(relx=0.5, rely=0.45, anchor="center")

    # ---------------------------------------------------------- 悬停 / 选中 / 展开

    def _card_at(self, x: int, y: int) -> dict[str, Any] | None:
        canvas_x = self._card_canvas.canvasx(x)
        canvas_y = self._card_canvas.canvasy(y)
        for card in self._card_layout:
            if card["x"] <= canvas_x <= card["x"] + card["w"] and card["y"] <= canvas_y <= card["y"] + card["h"]:
                return card
        return None

    def _on_card_motion(self, event) -> None:
        self._set_hover_card(self._card_at(event.x, event.y))

    def _set_hover_card(self, card: dict[str, Any] | None) -> None:
        if card is self._hover_card:
            return
        previous = self._hover_card
        self._hover_card = card
        if previous is not None:
            previous["hover"] = False
            self._repaint_card(previous)
        if card is not None:
            card["hover"] = True
            self._repaint_card(card)
        self._card_canvas.configure(cursor="hand2" if card is not None else "arrow")

    def _on_card_click(self, event) -> None:
        card = self._card_at(event.x, event.y)
        if card is None:
            return
        if card["path"] == self._card_detail_owner:
            # 再点一次收起详情，和折叠面板的直觉一致。
            self._collapse_card_detail()
            self._select_card(card["path"], expand=False)
            return
        self._select_card(card["path"], expand=True)

    def _on_card_double_click(self, event) -> None:
        card = self._card_at(event.x, event.y)
        if card is not None:
            self._open_directory(card["path"])

    def _card_by_path(self, path: str) -> dict[str, Any] | None:
        return self._card_index.get(path)

    def _select_card(self, path: str, expand: bool = False) -> None:
        """选中某张卡（同时同步右侧详情与状态栏），可选在卡内展开完整路径与操作。"""
        self._selected_path = path
        self._show_project_detail(self._projects_by_path.get(path))
        self._sync_card_selection()
        if expand:
            self._show_card_detail(path)
        self._scroll_card_into_view(path)

    def _sync_card_selection(self) -> None:
        for card in self._card_layout:
            selected = card["path"] == self._selected_path
            if card["selected"] == selected:
                continue
            card["selected"] = selected
            self._repaint_card(card)

    def _show_card_detail(self, path: str) -> None:
        if path == self._card_detail_owner:
            return
        self._collapse_card_detail(redraw=False)
        card = self._card_by_path(path)
        project = self._projects_by_path.get(path)
        if card is None or project is None:
            return

        box = ttk.Frame(self._card_canvas, style="DetailPath.TFrame")
        tk.Label(
            box, text=f"{DISPLAY_CREATED_DATE}  {project.created_date or EMPTY_VALUE}",
            background=DETAIL_BOX_BG, foreground=TEXT_SECONDARY, font=self.theme.card_body, anchor="w", justify="left",
        ).pack(fill="x", padx=10, pady=(9, 2))
        tk.Label(
            box, text=self._card_path_text(project.path), background=DETAIL_BOX_BG,
            foreground=TEXT_SECONDARY, font=self.theme.small, anchor="w", justify="left",
            wraplength=max(120, card["w"] - 2 * self.theme.card_pad - 20),
        ).pack(fill="x", padx=10)

        # 卡内宽度随分栏变化：主操作占满一行，两个次操作平分下一行，
        # 这样窄卡（260 px）下也不会把按钮文字截断。
        actions = ttk.Frame(box, style="DetailPath.TFrame")
        actions.pack(fill="x", padx=10, pady=(7, 9))
        ttk.Button(
            actions, text=DETAIL_OPEN_DIR, style="CompactPrimary.TButton",
            command=self.open_selected_project,
        ).pack(fill="x")
        secondary = ttk.Frame(actions, style="DetailPath.TFrame")
        secondary.pack(fill="x", pady=(5, 0))
        ttk.Button(
            secondary, text=DETAIL_COPY_PATH, style="CompactSoft.TButton",
            command=self.copy_selected_path,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(
            secondary, text=DETAIL_OPEN_PROGRAM, style="CompactSoft.TButton",
            command=self.open_selected_program_dir,
        ).pack(side="left", fill="x", expand=True)

        self._card_detail_frame = box
        self._card_detail_owner = path
        self._card_detail_index = card["index"]
        # 详情区高度按实际内容量一次：路径长短会影响换行行数。
        box.update_idletasks()
        self._card_detail_height = max(
            self.theme.card_detail_min, box.winfo_reqheight() + self.theme.card_pad + dpi.scaled(6, self._scale)
        )
        self._card_detail_window = self._card_canvas.create_window(
            card["x"] + self.theme.card_pad, card["y"] + self.theme.card_height - self.theme.card_pad + 4, window=box, anchor="nw",
            tags="card_detail",
        )
        for widget in (box, actions, secondary):
            widget.bind("<MouseWheel>", self._on_card_mousewheel)

        # 展开的那一行变高：整墙重排一次（151 张卡约 50 ms）。
        self._draw_cards(self._card_canvas.winfo_width())

    def _card_path_text(self, path: str) -> str:
        """卡内只显示相对主路径的部分：完整路径又长又重复，尾部才是关键信息。"""
        base = self.path_var.get().strip()
        if base:
            try:
                relative = os.path.relpath(path, base)
            except ValueError:
                relative = path
            if not relative.startswith(".."):
                return f"{CARD_PATH_PREFIX}{relative}"
        return path

    def _collapse_card_detail(self, redraw: bool = True) -> None:
        had_detail = self._card_detail_frame is not None
        if self._card_detail_window is not None:
            self._card_canvas.delete(self._card_detail_window)
        if self._card_detail_frame is not None:
            self._card_detail_frame.destroy()
        self._card_detail_frame = None
        self._card_detail_window = None
        self._card_detail_owner = None
        self._card_detail_index = None
        self._card_detail_height = self.theme.card_detail_min
        if had_detail and redraw and self._card_layout:
            self._draw_cards(self._card_canvas.winfo_width())

    def _scroll_card_into_view(self, path: str) -> None:
        card = self._card_by_path(path)
        canvas = self._card_canvas
        if card is None:
            return
        region = canvas.bbox("all")
        if not region or region[3] <= region[1]:
            return
        total = max(1, region[3] - region[1])
        view_top = canvas.canvasy(0)
        view_height = canvas.winfo_height()
        if card["y"] >= view_top and card["y"] + card["h"] <= view_top + view_height:
            return
        canvas.yview_moveto(min(1.0, max(0.0, (card["y"] - self.theme.card_gap) / total)))

    def _on_sort_changed(self) -> None:
        if self._view_mode == VIEW_MODE_CARDS:
            self._rebuild_cards(self._filtered_projects)
        else:
            self.update_table()

    def _refresh_card_times(self) -> None:
        """开发时间变化时只改真正变了的那几张卡（通常一次只有 1-2 张）。"""
        if self._view_mode != VIEW_MODE_CARDS or not self._card_layout:
            return
        seconds_map = self.work_time_service.get_project_seconds_bulk(
            [card["path"] for card in self._card_layout]
        )
        for card in self._card_layout:
            seconds = seconds_map.get(card["path"], (0, 0))
            if seconds == card["seconds"]:
                continue
            card["seconds"] = seconds
            if card["fields"] is not None:
                self._card_canvas.itemconfigure(
                    card["fields"], text=self._card_fields_text(card["project"], seconds)
                )

    def schedule_table_refresh(self, delay_ms: int = 180) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(delay_ms, self._refresh_table_from_search)

    def _refresh_table_from_search(self) -> None:
        self._search_after_id = None
        self.update_table()

    def _set_loading_state(self, loading: bool) -> None:
        self._load_in_progress = loading
        state = "disabled" if loading else "normal"
        combo_state = "disabled" if loading else "readonly"

        # 读目录期间先锁住可交互控件，避免用户同时改筛选条件导致状态跳来跳去。
        self.entry_path.configure(state=state)
        self.btn_browse.configure(state=state)
        self.btn_load.configure(state=state)
        self.btn_stats.configure(state=state)
        self.btn_new_project.configure(state=state)
        self.btn_settings_top.configure(state=state)
        self.btn_clear_search.configure(state=state)
        self.entry_search_keyword.configure(state=state)
        self.combo_year.configure(state=combo_state)
        self.combo_sales.configure(state=combo_state)
        self.combo_client.configure(state=combo_state)
        self.combo_chip.configure(state=combo_state)
        self.combo_package.configure(state=combo_state)
        self.sort_combo.configure(state=combo_state)
        self._update_search_controls()

        if loading:
            self.status_var.set(LOADING_TABLE_TEXT)
            self.empty_state_label.configure(text=LOADING_TABLE_TEXT)
            self.empty_state_label.place(relx=0.5, rely=0.52, anchor="center")
            self.card_empty_label.configure(text=LOADING_TABLE_TEXT)
            self.card_empty_label.place(relx=0.5, rely=0.45, anchor="center")

    def _update_search_controls(self) -> None:
        """让清空按钮和搜索状态保持一致，避免空搜索时出现可点击的死按钮。"""
        if self._load_in_progress:
            self.btn_clear_search.configure(state="disabled")
        elif self.search_keyword_var.get().strip():
            self.btn_clear_search.configure(state="normal")
        else:
            self.btn_clear_search.configure(state="disabled")

    def _update_empty_state(self, has_rows: bool) -> None:
        if has_rows or self._load_in_progress:
            self.empty_state_label.place_forget()
            return
        has_any_data = bool(self.all_projects)
        self.empty_state_label.configure(text=EMPTY_FILTER_TEXT if has_any_data else EMPTY_TABLE_TEXT)
        self.empty_state_label.place(relx=0.5, rely=0.52, anchor="center")

    def _apply_column_widths(self) -> None:
        for column, width in self._column_widths.items():
            self.tree.column(column, width=width, stretch=False)

    def _apply_settings(self) -> None:
        self._apply_timing_settings()
        self.work_time_service.set_enabled(self.settings.auto_track_work_time)
        if self.settings.auto_load_last_path and self.settings.last_base_path:
            self.path_var.set(self.settings.last_base_path)
            self.after(200, lambda: self.load_projects(notify_on_complete=False))

    def _apply_timing_settings(self) -> None:
        # 把设置里的三个计时参数下发给统计服务，改完立即生效、不用重启。
        self.work_time_service.configure_timing(
            TimingSettings(
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                active_window_seconds=self.settings.active_window_seconds,
                switch_grace_seconds=self.settings.switch_grace_seconds,
            )
        )

    def _save_settings(self) -> None:
        self.settings.last_base_path = self.path_var.get().strip()
        self.settings_service.save(self.settings)

    def choose_path(self) -> None:
        path = filedialog.askdirectory(title=CHOOSE_PATH_TITLE)
        if path:
            self.path_var.set(path)
            self._save_settings()

    def show_new_project(self, parent: tk.Misc | None = None) -> None:
        """按现有命名规则（序号-业务员-客户编号-项目名-YYYYMMDD）新建项目目录。"""
        base_path = self.path_var.get().strip()
        if not os.path.isdir(base_path):
            messagebox.showwarning(PROMPT_TITLE, INVALID_PATH_MESSAGE, parent=parent or self)
            return

        owner = parent if parent is not None else self
        win = tk.Toplevel(owner)
        win.title(NEW_PROJECT_TITLE)
        win.geometry("600x520")
        win.minsize(560, 500)
        win.configure(background=APP_BG)
        win.transient(owner)
        win.grab_set()

        frame = ttk.Frame(win, style="Band.TFrame", padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        # 主目录（只读展示，避免误改主路径）
        ttk.Label(frame, text=NEW_PROJECT_BASE_LABEL, style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        base_var = tk.StringVar(value=base_path)
        ttk.Entry(frame, textvariable=base_var, state="readonly").grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(6, 12)
        )

        salesman_var = tk.StringVar()
        sequence_var = tk.StringVar()
        client_var = tk.StringVar()
        date_var = tk.StringVar(value=date.today().isoformat())
        name_var = tk.StringVar()

        ttk.Label(frame, text=NEW_PROJECT_SALESMAN_LABEL, style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(frame, text=NEW_PROJECT_SEQUENCE_LABEL, style="Muted.TLabel").grid(row=2, column=2, sticky="w")
        # 业务员支持从已有列表选择，也允许输入新业务员；新业务员会自动从 001 开始。
        salesman_box = ttk.Combobox(frame, textvariable=salesman_var, values=self.sales_list)
        salesman_box.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 12), pady=(4, 2))
        ttk.Entry(frame, textvariable=sequence_var, width=10, state="readonly").grid(
            row=3, column=2, sticky="ew"
        )
        ttk.Label(frame, text=NEW_PROJECT_SEQUENCE_HINT, style="Muted.TLabel").grid(
            row=4, column=2, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text=NEW_PROJECT_CLIENT_LABEL, style="Muted.TLabel").grid(row=5, column=0, sticky="w")
        ttk.Label(frame, text=NEW_PROJECT_DATE_LABEL, style="Muted.TLabel").grid(row=5, column=2, sticky="w")
        ttk.Entry(frame, textvariable=client_var).grid(row=6, column=0, columnspan=2, sticky="ew", padx=(0, 12))
        ttk.Entry(frame, textvariable=date_var).grid(row=6, column=2, columnspan=2, sticky="ew")
        ttk.Label(frame, text=NEW_PROJECT_DATE_HINT, style="Muted.TLabel").grid(
            row=7, column=2, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text=NEW_PROJECT_NAME_LABEL, style="Muted.TLabel").grid(row=8, column=0, sticky="w")
        ttk.Entry(frame, textvariable=name_var).grid(row=9, column=0, columnspan=4, sticky="ew")
        ttk.Label(
            frame,
            text=f"{NEW_PROJECT_NAME_HINT}；{NEW_PROJECT_NAME_CALIBRATE_HINT}",
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=10, column=0, columnspan=4, sticky="w", pady=(0, 12))

        preview_box = ttk.Frame(frame, style="Band.TFrame", padding=12)
        preview_box.grid(row=11, column=0, columnspan=4, sticky="ew")
        preview_box.columnconfigure(0, weight=1)
        ttk.Label(preview_box, text=NEW_PROJECT_PREVIEW_LABEL, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        preview_var = tk.StringVar()
        ttk.Label(preview_box, textvariable=preview_var, style="Band.TLabel",
                  font=self.theme.section, wraplength=520, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))

        calibrating_name = False

        def calibrate_from_project_name(*_args) -> None:
            """用户粘贴完整项目片段时，自动校准业务员/客户/日期/纯项目名。

            普通名称（如“凸点振动球”）不做猜测，用户仍可自由修改已校准的字段。
            """
            nonlocal calibrating_name
            if calibrating_name:
                return
            parsed = self.project_service.parse_project_identity(name_var.get())
            if parsed is None:
                return
            salesman, client, project_name, created_date = parsed
            calibrating_name = True
            try:
                salesman_var.set(salesman)
                client_var.set(client)
                date_var.set(created_date)
                name_var.set(project_name)
            finally:
                calibrating_name = False

        def refresh_sequence(*_args) -> None:
            """序号只由年份和业务员决定，输入框只读，避免手工改乱目录编号。"""
            salesman = salesman_var.get().strip()
            if not salesman:
                sequence_var.set("")
                return
            try:
                sequence_var.set(
                    self.project_service.suggest_next_sequence(
                        base_path, salesman, date_var.get().strip()
                    )
                )
            except Exception:  # noqa: BLE001 - 自动建议失败不应阻止手动创建
                self.logger.exception("Failed to refresh project sequence")
                sequence_var.set("001")

        def refresh_preview(*_args) -> None:
            # 只负责刷新底部的目录名预览，不再回填输入框——
            # 否则 trace 会在每次改值时把建议值重新灌回去，造成内容被追加。
            sequence = sequence_var.get().strip()
            salesman = salesman_var.get().strip()
            client = client_var.get().strip()
            name = name_var.get().strip()
            parts = [sequence or "序号", salesman or "业务员", client or "客户编号", name or "新项目"]
            date_text = date_var.get().strip()
            date_suffix = date_text.replace("-", "") or "YYYYMMDD"
            try:
                year_folder = date.fromisoformat(date_text).strftime("%Y")
            except ValueError:
                year_folder = "年份"
            owner_folder = salesman or "业务员"
            stem = "-".join(parts) + "-" + date_suffix
            target_preview = os.path.join(base_path, year_folder, owner_folder, stem)
            preview_var.set(f"{stem}\n{target_preview}")

        def suggest_initial_values() -> None:
            # 仅在打开对话框时建议一次默认值：业务员/客户取最近用过的，
            # 序号按选定年份和业务员实时计算。
            try:
                if not salesman_var.get():
                    salesman_var.set(self.project_service.suggest_salesman(base_path) or "")
            except Exception:      # noqa: BLE001 - 建议值失败不影响手动填写
                self.logger.exception("Failed to suggest salesman")
            try:
                if not client_var.get():
                    client_var.set(self.project_service.suggest_client(base_path) or "")
            except Exception:      # noqa: BLE001
                self.logger.exception("Failed to suggest client")
            refresh_sequence()
            refresh_preview()

        salesman_box.bind("<<ComboboxSelected>>", refresh_sequence)
        for var in (sequence_var, salesman_var, client_var, name_var, date_var):
            var.trace_add("write", refresh_preview)
        salesman_var.trace_add("write", refresh_sequence)
        date_var.trace_add("write", refresh_sequence)
        name_var.trace_add("write", calibrate_from_project_name)
        suggest_initial_values()

        def create() -> None:
            sequence = sequence_var.get().strip()
            salesman = salesman_var.get().strip()
            client = client_var.get().strip()
            name = name_var.get().strip()
            date_text = date_var.get().strip()
            if not (sequence and salesman and client and name and date_text):
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_REQUIRED, parent=win)
                return
            if any(ch in salesman for ch in '\\/:*?"<>|'):
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_INVALID_SALESMAN, parent=win)
                return
            if any(ch in name for ch in '\\/:*?"<>|'):
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_INVALID_NAME, parent=win)
                return
            try:
                parsed_date = date.fromisoformat(date_text)
            except ValueError:
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_BAD_DATE, parent=win)
                return

            # 创建前重新计算一次，确保对话框打开期间有其他新增项目时也不会复用旧序号。
            sequence = self.project_service.suggest_next_sequence(base_path, salesman, date_text)
            sequence_var.set(sequence)

            folder = f"{sequence}-{salesman}-{client}-{name}-{parsed_date.strftime('%Y%m%d')}"
            # 目录固定落在“读取主目录 / 年份 / 业务员 / 项目目录”，
            # 不再把项目直接创建在主目录根下。
            target_parent = os.path.abspath(os.path.join(base_path, parsed_date.strftime("%Y"), salesman))
            target = os.path.join(target_parent, folder)
            if os.path.exists(target):
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_EXISTS.format(path=target), parent=win)
                return
            # 创建前先把完整的“主目录/年份/业务员/项目目录”路径摆给用户确认。
            if not messagebox.askyesno(
                NEW_PROJECT_TITLE, NEW_PROJECT_CONFIRM.format(path=target), parent=win
            ):
                return
            try:
                target = self.project_service.create_project_directory(
                    base_path, sequence, salesman, client, name, date_text
                )
            except FileExistsError:
                messagebox.showwarning(PROMPT_TITLE, NEW_PROJECT_EXISTS.format(path=target), parent=win)
                return
            except OSError as exc:
                self.logger.error("Failed to create project folder %s: %s", target, exc)
                message = NEW_PROJECT_FAILED.format(error=exc)
                if is_low_integrity():
                    # 低完整性进程没法在中等完整性的数据盘上建目录（WinError 5），
                    # 和"打不开文件夹"是同一个原因，一并说明。
                    message += NEW_PROJECT_LOW_INTEGRITY_HINT
                messagebox.showerror(ERROR_TITLE, message, parent=win)
                return

            self.logger.info("Created project folder %s", target)
            win.destroy()
            messagebox.showinfo(SUCCESS_TITLE, NEW_PROJECT_OK.format(path=target), parent=self)
            self.refresh_after_new_project()

        buttons = ttk.Frame(frame, style="Band.TFrame")
        buttons.grid(row=12, column=0, columnspan=4, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text=SETTINGS_CANCEL_TEXT, command=win.destroy, style="Soft.TButton").pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(buttons, text=NEW_PROJECT_CREATE_TEXT, command=create, style="Primary.TButton").pack(side="right")

        salesman_box.focus_set()

    def refresh_after_new_project(self) -> None:
        # 新项目是刚建的空目录，直接读它会出现"未读到任何项目"，因此重读整个主路径。
        if messagebox.askyesno(PROMPT_TITLE, NEW_PROJECT_ASK_LOAD, parent=self):
            self.load_projects()

    def clear_search(self) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        self.search_keyword_var.set("")
        self.update_table()

    def show_about(self) -> None:
        about_message = (
            f"{ABOUT_MESSAGE}\n\n"
            f"版本：{APP_VERSION}（{APP_BUILD_DATE}）\n"
            f"配置：{self.settings_service.config_path}\n"
            f"日志：{self.settings_service.config_dir / 'logs' / 'project_stats.log'}\n"
            f"开发时间：{self.work_time_service.record_path}"
        )
        messagebox.showinfo(ABOUT_TITLE, about_message)

    # ------------------------------------------------------------ 设置窗口

    def show_settings(self, parent: tk.Misc | None = None) -> None:
        # 允许从统计图窗口打开设置：那时主窗口可能已经缩到托盘，
        # 用统计窗口当 owner 才能保证设置窗显示在正确的位置、不被主窗口挡住。
        owner = parent if parent is not None else self
        settings_window = tk.Toplevel(owner)
        settings_window.title(SETTINGS_TITLE)
        settings_window.geometry("640x540")
        settings_window.minsize(600, 480)
        settings_window.resizable(True, True)
        settings_window.configure(background=APP_BG)
        settings_window.transient(owner)
        settings_window.grab_set()

        # 输入控件绑定到实例变量：标签页来回切换时不会丢用户已经改动的内容。
        self._settings_close_action_var = tk.StringVar(value=self.settings.close_action)
        self._settings_auto_load_var = tk.BooleanVar(value=self.settings.auto_load_last_path)
        self._settings_single_instance_var = tk.BooleanVar(value=self.settings.single_instance)
        self._settings_auto_track_var = tk.BooleanVar(value=self.settings.auto_track_work_time)
        self._settings_search_field_vars = {
            field: tk.BooleanVar(value=field in self.settings.search_fields)
            for field in DEFAULT_SEARCH_FIELDS
        }
        self._settings_timing_vars = {
            attr: tk.StringVar(value=str(getattr(self.settings, attr, default)))
            for _label, _hint, attr, default, _minimum in SETTINGS_TIMING_SPECS
        }

        # 底部按钮固定，不随标签页滚动。
        button_frame = ttk.Frame(settings_window, padding=(16, 10, 16, 14))
        button_frame.pack(side="bottom", fill="x")
        ttk.Button(
            button_frame, text=SETTINGS_SAVE_TEXT, style="Primary.TButton",
            command=lambda: self._save_settings_window(settings_window),
        ).pack(side="right")
        ttk.Button(
            button_frame, text=SETTINGS_RESET_TEXT, style="Soft.TButton",
            command=self._reset_settings_window,
        ).pack(side="right", padx=(0, 8))
        ttk.Button(
            button_frame, text=SETTINGS_CANCEL_TEXT, style="Soft.TButton",
            command=settings_window.destroy,
        ).pack(side="right", padx=(0, 8))

        notebook = ttk.Notebook(settings_window, style="Settings.TNotebook")
        notebook.pack(fill="both", expand=True, padx=16, pady=(14, 8))

        notebook.add(self._build_general_tab(notebook), text=SETTINGS_TAB_GENERAL)
        notebook.add(self._build_work_time_tab(notebook), text=SETTINGS_TAB_WORK_TIME)
        notebook.add(self._build_search_tab(notebook), text=SETTINGS_TAB_SEARCH)

    def _new_settings_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, style="Band.TFrame", padding=16)
        tab.columnconfigure(0, weight=1)
        return tab

    def _build_general_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = self._new_settings_tab(notebook)
        tab.columnconfigure(1, weight=1)

        ttk.Label(tab, text=SETTINGS_CLOSE_LABEL, style="PanelSection.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Radiobutton(
            tab, text=SETTINGS_CLOSE_BACKGROUND,
            value=DEFAULT_CLOSE_ACTION, variable=self._settings_close_action_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 6))
        ttk.Radiobutton(
            tab, text=SETTINGS_CLOSE_EXIT,
            value=EXIT_CLOSE_ACTION, variable=self._settings_close_action_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        ttk.Separator(tab, style="Panel.TSeparator").grid(row=3, column=0, columnspan=2, sticky="ew", pady=16)
        ttk.Checkbutton(
            tab, text=SETTINGS_AUTO_LOAD_PATH, variable=self._settings_auto_load_var
        ).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            tab, text=SETTINGS_SINGLE_INSTANCE, variable=self._settings_single_instance_var
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(tab, text=SETTINGS_RESTART_REQUIRED, style="PanelMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=(22, 0)
        )
        return tab

    def _build_work_time_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = self._new_settings_tab(notebook)
        # 四列：标签 | 输入框 | 单位 | 说明（说明占满右侧剩余宽度）
        tab.columnconfigure(3, weight=1)

        ttk.Checkbutton(
            tab, text=SETTINGS_AUTO_TRACK_WORK_TIME, variable=self._settings_auto_track_var
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            tab,
            text=SETTINGS_WORK_TIME_PATH_LABEL.format(path=self.work_time_service.record_path),
            style="PanelMuted.TLabel",
            wraplength=520,
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=(22, 0), pady=(2, 0))

        ttk.Separator(tab, style="Panel.TSeparator").grid(row=2, column=0, columnspan=4, sticky="ew", pady=14)

        for index, (label, hint, attr, _default, _minimum) in enumerate(SETTINGS_TIMING_SPECS):
            row = 3 + index
            ttk.Label(tab, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(tab, textvariable=self._settings_timing_vars[attr], width=8).grid(
                row=row, column=1, sticky="w", padx=(14, 4), pady=6
            )
            ttk.Label(tab, text=SETTINGS_SECONDS_SUFFIX, style="Panel.TLabel").grid(
                row=row, column=2, sticky="w", padx=(0, 14), pady=6
            )
            ttk.Label(tab, text=hint, style="PanelMuted.TLabel", wraplength=420).grid(
                row=row, column=3, sticky="w", pady=6
            )

        ttk.Label(tab, text=SETTINGS_TIMING_HINT, style="PanelMuted.TLabel", wraplength=520).grid(
            row=3 + len(SETTINGS_TIMING_SPECS), column=0, columnspan=4, sticky="w", pady=(14, 0)
        )
        return tab

    def _build_search_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = self._new_settings_tab(notebook)

        ttk.Label(tab, text=SETTINGS_SEARCH_FIELDS_LABEL, style="PanelSection.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        fields_frame = ttk.Frame(tab, style="Band.TFrame")
        fields_frame.grid(row=1, column=0, sticky="w", pady=(10, 0))
        for index, field in enumerate(DEFAULT_SEARCH_FIELDS):
            ttk.Checkbutton(
                fields_frame, text=field, variable=self._settings_search_field_vars[field]
            ).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 28), pady=(0, 8)
            )
        ttk.Label(tab, text=SETTINGS_SEARCH_FIELDS_HINT, style="PanelMuted.TLabel", wraplength=520).grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        return tab

    def _read_timing_settings(self, parent: tk.Misc) -> dict[str, int] | None:
        parsed: dict[str, int] = {}
        for _label, _hint, attr, _default, minimum in SETTINGS_TIMING_SPECS:
            text = self._settings_timing_vars[attr].get().strip()
            value = int(text) if text.isdigit() else -1
            if value < minimum or value > MAX_TIMING_SECONDS:
                messagebox.showwarning(
                    PROMPT_TITLE,
                    SETTINGS_TIMING_INVALID.format(minimum=minimum, maximum=MAX_TIMING_SECONDS),
                    parent=parent,
                )
                return None
            parsed[attr] = value
        return parsed

    def _save_settings_window(self, settings_window: tk.Toplevel) -> None:
        selected_search_fields = [
            field for field in DEFAULT_SEARCH_FIELDS
            if self._settings_search_field_vars[field].get()
        ]
        if not selected_search_fields:
            messagebox.showwarning(PROMPT_TITLE, SETTINGS_SEARCH_FIELDS_REQUIRED, parent=settings_window)
            return

        timing = self._read_timing_settings(settings_window)
        if timing is None:
            return

        self.settings.close_action = self._settings_close_action_var.get()
        self.settings.auto_load_last_path = self._settings_auto_load_var.get()
        self.settings.single_instance = self._settings_single_instance_var.get()
        self.settings.auto_track_work_time = self._settings_auto_track_var.get()
        self.settings.search_fields = selected_search_fields
        self.settings.idle_timeout_seconds = timing["idle_timeout_seconds"]
        self.settings.active_window_seconds = timing["active_window_seconds"]
        self.settings.switch_grace_seconds = timing["switch_grace_seconds"]
        self._save_settings()
        self._apply_timing_settings()
        self.work_time_service.set_enabled(self.settings.auto_track_work_time)
        settings_window.destroy()
        self.update_table()

    def _reset_settings_window(self) -> None:
        default_settings = self.settings_service.default_settings()
        self._settings_close_action_var.set(default_settings.close_action)
        self._settings_auto_load_var.set(default_settings.auto_load_last_path)
        self._settings_single_instance_var.set(default_settings.single_instance)
        self._settings_auto_track_var.set(default_settings.auto_track_work_time)
        for _label, _hint, attr, default, _minimum in SETTINGS_TIMING_SPECS:
            self._settings_timing_vars[attr].set(str(getattr(default_settings, attr, default)))
        for field, field_var in self._settings_search_field_vars.items():
            field_var.set(field in default_settings.search_fields)
        # 重置时只恢复产品默认值，不自动强改当前路径，避免用户误以为数据被删掉了。

    def handle_close(self) -> None:
        self._save_settings()
        if self.settings.close_action == DEFAULT_CLOSE_ACTION:
            self.is_background_hidden = True
            self.withdraw()
            self.logger.info("Main window hidden to tray")
            self.tray_service.start(self.request_show_from_tray, self.request_exit_from_tray)
            if not self.settings.background_notice_shown:
                # 这个提示只保留第一次，后面用户会默认知道程序已经缩到托盘了。
                self.settings.background_notice_shown = True
                self._save_settings()
                # 主窗口此刻已经 withdraw，必须显式指定 parent，否则提示框可能落到别的窗口后面。
                messagebox.showinfo(PROMPT_TITLE, BACKGROUND_NOTICE, parent=self)
            return
        self.exit_application()

    def request_show_from_tray(self) -> None:
        self._tray_show_requested.set()

    def request_exit_from_tray(self) -> None:
        self._tray_exit_requested.set()

    def restore_from_background(self) -> None:
        if self.is_background_hidden:
            self.tray_service.stop()
            self.deiconify()
            self.lift()
            self.focus_force()
            self.after(100, lambda: self.attributes('-topmost', False))
            self.is_background_hidden = False
            self.logger.info("Main window restored from tray")

    def activate_main_window(self) -> None:
        self.after(0, self._activate_main_window)

    def _activate_main_window(self) -> None:
        self.restore_from_background()
        self.deiconify()
        self.attributes('-topmost', True)
        self.lift()
        self.focus_force()
        self.state("normal")
        self.after(100, lambda: self.attributes('-topmost', False))

    def exit_application(self) -> None:
        if hasattr(self, "single_instance_manager"):
            self.single_instance_manager.stop()
        self.work_time_service.stop()
        self.tray_service.stop()
        self.destroy()

    def update_column_widths(self, projects: list[ProjectRecord] | None = None) -> None:
        # 列宽完全由可用宽度决定（见 _fit_columns_to_width），这里只是触发一次重算。
        self._fit_columns_to_width()

    def _apply_catalog(self, catalog: ProjectCatalog) -> None:
        self.all_projects = catalog.projects
        self.year_list = catalog.years
        self.sales_list = catalog.salesmen
        self.client_list = catalog.clients
        self.chip_list = catalog.chips
        self.package_list = catalog.packages
        self._projects_by_path = {p.path: p for p in self.all_projects}
        self._selected_path = None

        self.combo_year["values"] = [ALL_OPTION] + self.year_list
        self.combo_sales["values"] = [ALL_OPTION] + self.sales_list
        self.combo_client["values"] = [ALL_OPTION] + self.client_list
        self.combo_chip["values"] = [ALL_OPTION] + self.chip_list
        self.combo_package["values"] = [ALL_OPTION] + self.package_list
        self.combo_year.set(ALL_OPTION)
        self.combo_sales.set(ALL_OPTION)
        self.combo_client.set(ALL_OPTION)
        self.combo_chip.set(ALL_OPTION)
        self.combo_package.set(ALL_OPTION)
        # 载入新数据后按当前宽度重算一次列宽（列表内容变了，长文本列需要重新分配）。
        self._fit_columns_to_width()
        self._schedule_column_refit()
        self._update_summary(self.all_projects)
        self._configure_work_time_async(self.all_projects)
        self.status_var.set(f"已读取 {len(self.all_projects)} 个项目")

    def _configure_work_time_async(self, projects: list[ProjectRecord]) -> None:
        # configure_projects 会遍历所有项目的版本目录并建立基线，
        # 实测在真实数据上要 0.36-0.45 s。它纯属 I/O，放在主线程会让
        # "读取完成" 之后再卡一下，因此改到后台线程，完成后回主线程刷新表格。
        def worker() -> None:
            if self.all_projects is not projects:
                return  # 期间用户又切了主路径，这一批已经过期
            try:
                self.work_time_service.configure_projects(projects)
            except Exception:
                self.logger.exception("Failed to configure work-time tracking")
                return
            try:
                self.after(0, lambda: self._finish_configure_work_time(projects))
            except (tk.TclError, RuntimeError):
                # 窗口已销毁时 tkinter 会抛 TclError；解释器正在退出时
                # _register() 会抛 RuntimeError("main thread is not in main loop")。
                # 两者都属于"程序正在关闭"，忽略即可，但不能让它跑到线程外。
                return

        threading.Thread(target=worker, daemon=True).start()

    def _finish_configure_work_time(self, projects: list[ProjectRecord]) -> None:
        if not self.winfo_exists() or self.all_projects is not projects:
            return
        self.update_table()

    def load_projects(self, notify_on_complete: bool = True) -> None:
        if self._load_in_progress:
            return

        base_path = self.path_var.get().strip()
        if not base_path:
            if not notify_on_complete:
                return
            self.choose_path()
            base_path = self.path_var.get().strip()

        if not base_path:
            return

        if not os.path.isdir(base_path):
            # 目录不存在、或用户选中的其实是个文件，都在这里拦下，
            # 否则 os.listdir 会抛 NotADirectoryError，弹给用户一段 WinError 号。
            if notify_on_complete:
                messagebox.showwarning(PROMPT_TITLE, INVALID_PATH_MESSAGE)
            else:
                self.status_var.set("上次路径不可用，请重新选择项目主路径")
            return

        self.path_var.set(base_path)
        self._save_settings()
        self._load_token += 1
        load_token = self._load_token
        if self._load_timeout_id is not None:
            try:
                self.after_cancel(self._load_timeout_id)
            except tk.TclError:
                pass
            self._load_timeout_id = None
        self._set_loading_state(True)
        self.logger.info("Loading projects from %s", base_path)
        self._load_timeout_id = self.after(
            LOAD_TIMEOUT_MS,
            lambda token=load_token, path=base_path: self._handle_load_timeout(token, path),
        )

        def worker() -> None:
            try:
                catalog = self.project_service.load_projects(base_path)
            except Exception as exc:
                try:
                    self.after(0, lambda error=exc, token=load_token: self._finish_load_projects(
                        base_path, None, error, notify_on_complete, token
                    ))
                except (tk.TclError, RuntimeError):
                    return
                return
            try:
                self.after(0, lambda result=catalog, token=load_token: self._finish_load_projects(
                    base_path, result, None, notify_on_complete, token
                ))
            except (tk.TclError, RuntimeError):
                return

        # 目录扫描放到后台线程，主窗口就不会在大项目树上卡住。
        self._load_thread = threading.Thread(target=worker, daemon=True)
        self._load_thread.start()

    def _handle_load_timeout(self, token: int, base_path: str) -> None:
        """让失联网络盘不再把界面永久锁在“读取中”。"""
        if token != self._load_token or not self._load_in_progress:
            return
        self._load_timeout_id = None
        self._load_token += 1  # 丢弃稍后才返回的旧线程结果
        self._set_loading_state(False)
        self.status_var.set(LOAD_TIMEOUT_TEXT)
        self.logger.error("Loading projects timed out after %sms: %s", LOAD_TIMEOUT_MS, base_path)
        self._update_empty_state(bool(self.tree.get_children()))

    def _finish_load_projects(
        self,
        base_path: str,
        catalog: ProjectCatalog | None,
        error: Exception | None,
        notify_on_complete: bool = True,
        token: int | None = None,
    ) -> None:
        if not self.winfo_exists() or (token is not None and token != self._load_token):
            return

        if self._load_timeout_id is not None:
            try:
                self.after_cancel(self._load_timeout_id)
            except tk.TclError:
                pass
            self._load_timeout_id = None

        self._set_loading_state(False)

        if error is not None:
            self.logger.error("Failed to load projects from %s", base_path, exc_info=(type(error), error, error.__traceback__))
            self._update_empty_state(bool(self.tree.get_children()))
            if notify_on_complete:
                messagebox.showerror(ERROR_TITLE, str(error))
            else:
                self.status_var.set(f"自动读取失败：{error}")
            return

        if catalog is None:
            return

        self._apply_catalog(catalog)
        self.update_table()
        self.logger.info("Loaded %s projects from %s", len(self.all_projects), base_path)

        summary = catalog.load_summary
        extra_parts = []
        if summary.invalid_project_folders:
            extra_parts.append(f"跳过无效目录 {summary.invalid_project_folders} 个")
        if summary.unresolved_chip_name:
            extra_parts.append(f"芯片型号未识别 {summary.unresolved_chip_name} 个（根目录无标记文件）")
        if summary.unresolved_package:
            extra_parts.append(f"脚位未识别 {summary.unresolved_package} 个（标记文件名没写封装）")
        if summary.unreadable_directories:
            extra_parts.append(f"无法读取目录 {summary.unreadable_directories} 个")

        message = DONE_MESSAGE.format(count=len(self.all_projects))
        if not self.all_projects:
            # 0 个项目时把"可能选错了主路径"说清楚，否则用户会以为是自己数据为空。
            message = f"{message}\n\n{NONE_FOUND_MESSAGE}"
        if extra_parts:
            message = f"{message}\n\n" + "；".join(extra_parts)

        if notify_on_complete:
            messagebox.showinfo(DONE_TITLE, message)

    def update_table(self) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None

        projects = self.project_service.filter_projects(
            projects=self.all_projects,
            year=self.year_var.get() or ALL_OPTION,
            salesman=self.sales_var.get() or ALL_OPTION,
            client=self.client_var.get() or ALL_OPTION,
            chip=self.chip_var.get() or ALL_OPTION,
            package=self.package_var.get() or ALL_OPTION,
            search_fields=self.settings.search_fields,
            search_keyword=self.search_keyword_var.get(),
        )
        self._filtered_projects = projects

        if self._view_mode == VIEW_MODE_CARDS:
            # 卡片视图下表格不参与显示，行内容留到切回表格时再补（见 _apply_view_mode），
            # 这样每次筛选只付一次重建成本。
            self._clear_table_rows()
            self._update_empty_state(True)
            self._rebuild_cards(projects)
        else:
            self._fill_table(projects)
            self._update_empty_state(bool(projects))

        self.status_var.set(f"当前显示 {len(projects)} / {len(self.all_projects)} 个项目")
        # 信息卡与列表保持一致：展示当前筛选结果的统计
        self._update_summary(projects)

        # 尽量保持当前选中项；没有选中或已被过滤掉时，默认选中第一个，
        # 这样详情不会一直空着。
        visible_paths = {project.path for project in projects}
        target_path = self._selected_path if self._selected_path in visible_paths else None
        if target_path is None and projects:
            target_path = projects[0].path
        if target_path is not None:
            self._select_path(target_path)
        else:
            self._show_project_detail(None)

    def _clear_table_rows(self) -> None:
        self._set_hover_item(None)
        for item in self.tree.get_children():
            self.tree.delete(item)
        # 用 item id -> 路径 的映射代替"把路径当 tag"，双击时更可靠，也不依赖 tags 顺序。
        self._item_paths.clear()
        self._path_to_item.clear()

    def _fill_table(self, projects: list[ProjectRecord]) -> None:
        self._clear_table_rows()

        for index, project in enumerate(projects, start=1):
            row = project.to_display_dict(index)
            row_tag = "even" if index % 2 == 0 else "odd"
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    row[DISPLAY_SEQUENCE],
                    row[DISPLAY_YEAR],
                    row[DISPLAY_SALESMAN],
                    row[DISPLAY_CLIENT],
                    row[DISPLAY_PROJECT_NAME],
                    row[DISPLAY_CHIP_NAME],
                    row[DISPLAY_PACKAGE],
                    row[DISPLAY_CREATED_DATE],
                    row[DISPLAY_SAMPLE_COUNT],
                ),
                tags=(row_tag,),
            )
            self._item_paths[item_id] = project.path
            self._path_to_item[project.path] = item_id

    # ------------------------------------------------------------ 选中与详情

    def _select_path(self, path: str) -> None:
        if self._view_mode == VIEW_MODE_CARDS:
            # 卡片视图里没有表格行：选中卡片、同步详情，表格等切回去时再补。
            item_id = self._path_to_item.get(path)
            if item_id is not None:
                if self.tree.selection() != (item_id,):
                    self.tree.selection_set(item_id)
                self.tree.see(item_id)
            self._selected_path = path
            self._show_project_detail(self._projects_by_path.get(path))
            self._sync_card_selection()
            return

        item_id = self._path_to_item.get(path)
        if item_id is None:
            self._show_project_detail(None)
            return
        if self.tree.selection() != (item_id,):
            self.tree.selection_set(item_id)
        self.tree.see(item_id)
        self._show_project_detail(self._projects_by_path.get(path))

    def _on_tree_selection(self, event=None) -> None:
        # 更新表格时会重建所有行，这里只处理用户主动点击的选中。
        if self._suspend_selection_event:
            return
        selected = self.tree.selection()
        if not selected:
            return
        path = self._item_paths.get(selected[0])
        if path is None:
            return
        self._selected_path = path
        self._show_project_detail(self._projects_by_path.get(path))
        # 卡片墙上同步高亮，两个视图的选中状态始终一致。
        self._sync_card_selection()

    def _show_project_detail(self, project: ProjectRecord | None) -> None:
        if project is None:
            self._selected_path = None
            for var in self.detail_vars.values():
                var.set("—")
            self.detail_today_var.set("—")
            self.detail_total_var.set("—")
            self.status_var.set(DETAIL_EMPTY)
            return

        self._selected_path = project.path
        self.detail_vars["project_name"].set(project.project_name)
        self.detail_vars["salesman"].set(project.salesman)
        self.detail_vars["client"].set(project.client)
        self.detail_vars["chip_name"].set(project.chip_name)
        self.detail_vars["package_name"].set(project.package_name)
        self.detail_vars["created_date"].set(project.created_date)
        self.detail_vars["sample_count"].set(DETAIL_SAMPLE_TIMES.format(count=project.sample_count))
        self.detail_vars["path"].set(project.path)

        work_today, work_total = self.work_time_service.get_project_duration_text(project.path)
        self.detail_today_var.set(work_today)
        self.detail_total_var.set(work_total)

    def _update_summary(self, projects: list[ProjectRecord]) -> None:
        # 信息卡统计的是"当前列表里的项目"（即筛选/搜索结果），
        # 这样它和左边列表始终对得上，而不是永远显示全量总数。
        samples = sum(p.sample_count for p in projects)
        salesmen = len({p.salesman for p in projects if p.salesman})
        chips = len({p.chip_name for p in projects if p.chip_name})
        self.summary_vars[SUMMARY_PROJECTS].set(str(len(projects)))
        self.summary_vars[SUMMARY_SAMPLES].set(str(samples))
        self.summary_vars[SUMMARY_SALESMEN].set(str(salesmen))
        self.summary_vars[SUMMARY_CHIPS].set(str(chips))
        # 卡片视图没有右栏信息卡，这几个数字改在状态栏右侧显示。
        if self._view_mode == VIEW_MODE_CARDS:
            self.summary_inline_var.set(STATUS_SUMMARY.format(
                projects=len(projects), samples=samples, salesmen=salesmen, chips=chips
            ))
        else:
            self.summary_inline_var.set("")

    def request_work_time_refresh(self) -> None:
        try:
            self.after(0, self._refresh_work_time_display)
        except (tk.TclError, RuntimeError):
            return

    def _refresh_work_time_display(self) -> None:
        # 开发时间只影响右侧详情里的两行字和卡片上的累计时间，不必重建整张表。
        if self._selected_path:
            self._show_project_detail(self._projects_by_path.get(self._selected_path))
        self._refresh_card_times()

    def copy_selected_path(self) -> None:
        path = self._selected_path
        if not path:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(path)
            self.status_var.set(COPY_PATH_DONE)
        except tk.TclError as exc:
            self.logger.error("Failed to copy path: %s", exc)
            self.status_var.set(COPY_PATH_FAILED.format(error=exc))

    def open_selected_program_dir(self) -> None:
        path = self._selected_path
        if not path:
            return
        program_dir = os.path.join(path, "程序")
        if not os.path.isdir(program_dir):
            messagebox.showinfo(PROMPT_TITLE, PROGRAM_DIR_MISSING, parent=self)
            return
        self._open_directory(program_dir)

    def _open_directory(self, path: str) -> None:
        # 配置文件里可能保留了旧的混合斜杠路径；先转换成 Windows 的规范绝对路径。
        # 打开文件夹走 explorer.exe 而不是 os.startfile：它接受完整的规范路径，
        # 对中文、空格和历史上混用的分隔符都不挑剔；两者在低完整性环境下都会被系统
        # 拒绝，那种情况由下面的 is_low_integrity() 分支提前拦下并说明原因。
        normalized_path = os.path.normpath(os.path.abspath(os.fspath(path)))
        if not os.path.isdir(normalized_path):
            # 目录可能已被改名、移动或删除；不要把它变成 Tk 回调异常。
            self.logger.warning("Directory is no longer available: %s", normalized_path)
            self.status_var.set(OPEN_MISSING_MESSAGE)
            messagebox.showwarning(PROMPT_TITLE, OPEN_MISSING_MESSAGE, parent=self)
            return
        if is_low_integrity():
            # 低完整性进程调用资源管理器一定会被系统拒绝，这里提前说清楚原因，
            # 而不是等 explorer.exe 悄悄退出（用户看到的就是"点了没反应"）。
            self.logger.warning(
                "Cannot open %s: process runs at low integrity (move the app out of the "
                "Downloads folder or clear the folder's integrity label)",
                normalized_path,
            )
            self.status_var.set(OPEN_FAILED_MESSAGE.format(error="低完整性环境"))
            messagebox.showwarning(PROMPT_TITLE, OPEN_BLOCKED_LOW_INTEGRITY, parent=self)
            return
        try:
            if os.name == "nt":
                # explorer.exe 能正确处理包含中文、空格和混合历史分隔符的路径。
                process = subprocess.Popen(
                    ["explorer.exe", normalized_path],
                    close_fds=True,
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                )
                self._watch_opened_directory(process, normalized_path)
            else:
                os.startfile(normalized_path)
        except OSError as exc:
            # 某些精简 Windows 环境没有 explorer.exe，保留原 API 作为后备方案。
            try:
                os.startfile(normalized_path)
            except OSError:
                self.logger.error("Failed to open %s: %s", normalized_path, exc)
                self.status_var.set(OPEN_FAILED_MESSAGE.format(error=exc))
                messagebox.showerror(ERROR_TITLE, OPEN_FAILED_MESSAGE.format(error=exc), parent=self)

    def _watch_opened_directory(self, process: subprocess.Popen, path: str) -> None:
        """兜底检查：explorer.exe 起不来时不会抛异常，只能看它的退出码。

        成功把路径转交给资源管理器时 explorer.exe 会立刻退出并返回 0/1；
        仍然在运行说明它自己开了新窗口，也属正常。
        出现别的退出码（例如低完整性下的 0xC0000142）说明系统拒绝了这次调用，
        这里补一条明确提示，避免"点了完全没反应"。
        """
        def check() -> None:
            if process.poll() is None or process.returncode in (0, 1):
                return
            code = process.returncode & 0xFFFFFFFF
            self.logger.error(
                "explorer.exe refused to open %s (exit code 0x%08X)", path, code
            )
            message = OPEN_FAILED_MESSAGE.format(error=f"explorer.exe 退出码 0x{code:08X}")
            self.status_var.set(message)
            messagebox.showwarning(PROMPT_TITLE, message, parent=self)

        try:
            self.after(1200, check)
        except (tk.TclError, RuntimeError):
            # 窗口已销毁：这次检查没有意义，忽略。
            return

    def open_selected_project(self, event=None) -> None:
        if self._view_mode == VIEW_MODE_CARDS:
            # 卡片视图下不维护表格行，直接打开当前选中的项目。
            path = self._selected_path
        else:
            selected = self.tree.selection()
            path = self._item_paths.get(selected[0]) if selected else self._selected_path
        if not path:
            return
        self._open_directory(path)

    @staticmethod
    def _load_chart_modules() -> tuple[Any, Any, Any, Any]:
        # matplotlib 的导入本身就要 0.6 s 以上；只有真正要看统计图时才付这个代价。
        # use("TkAgg") 必须早于 import pyplot，否则 matplotlib 会去探测后端，反而更慢。
        import matplotlib

        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        import mplcursors
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        return plt, mplcursors, FigureCanvasTkAgg, matplotlib

    def show_statistics(self) -> None:
        self.restore_from_background()

        if not self.all_projects:
            messagebox.showinfo(PROMPT_TITLE, LOAD_FIRST_MESSAGE)
            return

        stat_window = getattr(self, "stat_window", None)
        if stat_window is not None:
            try:
                still_open = bool(stat_window.winfo_exists())
            except tk.TclError:
                still_open = False
            if still_open:
                stat_window.lift()
                stat_window.focus_force()
                return

        plt, mplcursors, FigureCanvasTkAgg, matplotlib = self._load_chart_modules()
        # 不同 Windows 镜像的中文字体名称不完全一致；优先使用已安装字体，
        # 避免统计图标题/坐标轴变成方框。界面主题已经解析过一次可用家族，
        # 这里先试它（保证图表和界面同一种中文字体），再退到常见字体名。
        installed_fonts = set(tkfont.families(self))
        chart_fonts = [
            self.theme.family,
            "Microsoft YaHei", "Microsoft JhengHei", "SimSun",
            "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "Segoe UI",
        ]
        matplotlib.rcParams["font.sans-serif"] = [name for name in chart_fonts if name in installed_fonts] or ["DejaVu Sans"]
        matplotlib.rcParams["axes.unicode_minus"] = False

        win = tk.Toplevel(self)
        self.stat_window = win
        win.title(STAT_WINDOW_TITLE)
        win.geometry("760x620")
        win.configure(background=APP_BG)
        win.focus_force()

        # 统计图每次切换条件都会重建，关闭前把旧 figure 释放掉，避免 Matplotlib 对象越堆越多。
        current_canvas: Any = None
        current_fig: Any = None

        def clear_chart() -> None:
            nonlocal current_canvas, current_fig
            if current_canvas is not None:
                current_canvas.get_tk_widget().destroy()
                current_canvas = None
            if current_fig is not None:
                plt.close(current_fig)
                current_fig = None

        def close_window() -> None:
            clear_chart()
            win.destroy()

        win.bind("<Escape>", lambda e: close_window())
        win.protocol("WM_DELETE_WINDOW", close_window)

        frame_top = ttk.Frame(win, style="Band.TFrame", padding=(16, 14))
        frame_top.pack(fill="x", padx=16, pady=(16, 10))

        ttk.Label(frame_top, text=STAT_YEAR_LABEL, style="Band.TLabel", font=self.theme.ui).pack(side="left")
        year_var = tk.StringVar()
        combo_year = ttk.Combobox(frame_top, textvariable=year_var, state="readonly", width=10)
        combo_year["values"] = [ALL_OPTION] + self.year_list
        combo_year.set(ALL_OPTION)
        combo_year.pack(side="left", padx=5)

        ttk.Label(frame_top, text=STAT_TYPE_LABEL, style="Band.TLabel", font=self.theme.ui).pack(side="left", padx=(15, 0))
        stat_type_var = tk.StringVar(value=STAT_SALESMAN)
        combo_stat_type = ttk.Combobox(frame_top, textvariable=stat_type_var, state="readonly", width=10)
        combo_stat_type["values"] = [STAT_SALESMAN, STAT_CHIP_NAME]
        combo_stat_type.pack(side="left", padx=5)

        btn_save = ttk.Button(frame_top, text=SAVE_CHART_TEXT, style="Primary.TButton")
        btn_save.pack(side="right")
        ttk.Button(
            frame_top,
            text=SETTINGS_TITLE,
            style="CompactSoft.TButton",
            command=lambda: self.show_settings(parent=win),
        ).pack(side="right", padx=(0, 8))

        chart_frame = ttk.Frame(win, style="Band.TFrame", padding=(10, 10, 10, 12))
        chart_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        def draw_chart() -> None:
            nonlocal current_canvas, current_fig
            clear_chart()
            btn_save.state(["disabled"])

            selected_year = year_var.get()
            data = [
                project for project in self.all_projects
                if selected_year == ALL_OPTION or project.year == selected_year
            ]

            stat_type = stat_type_var.get()
            stats = self.project_service.build_statistics(data, stat_type)
            if not stats:
                messagebox.showinfo(PROMPT_TITLE, NO_DATA_MESSAGE.format(year=selected_year))
                return

            fig, ax = plt.subplots(figsize=(7.2, 4.5))
            current_fig = fig
            fig.patch.set_facecolor(PANEL_BG)
            ax.set_facecolor(PANEL_BG)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color(LINE)
            ax.spines["bottom"].set_color(LINE)
            ax.tick_params(colors=TEXT_SECONDARY)
            ax.grid(axis="y", color=CHART_GRID, linewidth=0.8)
            bars = ax.bar(stats.keys(), stats.values(), color=ACCENT)
            title_prefix = selected_year if selected_year != ALL_OPTION else ALL_YEARS_TEXT
            ax.set_title(
                f"{title_prefix}{stat_type}{Y_AXIS_LABEL}",
                fontsize=13,
                color=TEXT_PRIMARY,
            )
            ax.set_xlabel(stat_type, fontsize=11, color=TEXT_SECONDARY)
            ax.set_ylabel(Y_AXIS_LABEL, fontsize=11, color=TEXT_SECONDARY)
            plt.tight_layout(pad=1.2)

            cursor = mplcursors.cursor(bars, hover=True)

            @cursor.connect("add")
            def on_hover(sel):
                for bar in bars:
                    bar.set_color(ACCENT)
                bars[sel.index].set_color(CHART_SELECTED)
                name = list(stats.keys())[sel.index]
                value = list(stats.values())[sel.index]
                sel.annotation.set_text(HOVER_TEXT.format(name=name, value=value))
                sel.annotation.get_bbox_patch().set(fc=PANEL_BG, ec=LINE, alpha=0.98)

            current_canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            current_canvas.draw()
            current_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

            def save_chart() -> None:
                file_path = filedialog.asksaveasfilename(
                    parent=win,
                    title=SAVE_CHART_TITLE,
                    defaultextension=".png",
                    initialfile=SAVE_CHART_FILE.format(year=selected_year),
                    filetypes=[("PNG", "*.png"), ("JPG", "*.jpg")],
                )
                if file_path:
                    try:
                        fig.savefig(file_path, dpi=300, bbox_inches="tight")
                        messagebox.showinfo(SUCCESS_TITLE, SAVE_SUCCESS_MESSAGE.format(path=file_path))
                    except Exception as exc:
                        messagebox.showerror(ERROR_TITLE, SAVE_ERROR_MESSAGE.format(error=exc))

            btn_save.config(command=save_chart)
            btn_save.state(["!disabled"])

        draw_chart()
        combo_year.bind("<<ComboboxSelected>>", lambda e: draw_chart())
        combo_stat_type.bind("<<ComboboxSelected>>", lambda e: draw_chart())


def main() -> None:
    app = ProjectBrowser()
    app.mainloop()


if __name__ == "__main__":
    main()
