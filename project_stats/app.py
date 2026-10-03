import logging
import sys
from pathlib import Path


if __package__ in (None, ""):
    workspace_root = Path(__file__).resolve().parent.parent
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

from project_stats.app_info import APP_NAME, APP_VERSION
from project_stats.config import SettingsService
from project_stats.runtime import SingleInstanceManager
from project_stats.runtime.app_logging import setup_logging
from project_stats.runtime.app_paths import get_app_root
from project_stats.runtime.integrity import describe_integrity, is_low_integrity
from project_stats.ui.main_window import APP_TITLE, ProjectBrowser


def main() -> None:
    try:
        # 单实例判定必须在建窗之前完成：否则第二个实例会先读配置、先建 UI，
        # 甚至因为"启动时恢复上次路径"而启动目录扫描并回写 settings.json。
        # 句柄需要活到进程结束，因此这里保留引用，不能写成一次性调用后丢弃。
        single_instance_manager: SingleInstanceManager | None = None
        settings = SettingsService().load()
        if settings.single_instance:
            single_instance_manager = SingleInstanceManager(APP_TITLE)
            if not single_instance_manager.start_or_activate_existing():
                # 命中已有实例：start_or_activate_existing() 内部已释放句柄，直接退出。
                return

        log_path = setup_logging(get_app_root())
        logger = logging.getLogger("project_stats")
        logger.info("Starting %s %s", APP_NAME, APP_VERSION)
        logger.info("Log file: %s", log_path)
        # 完整性级别决定能不能调用资源管理器 / 往数据盘写文件，
        # 出问题时第一个要看的就是这一行。
        logger.info("Process integrity: %s", describe_integrity())
        if is_low_integrity():
            logger.warning(
                "Running at low integrity: opening folders and creating directories "
                "outside the app folder will be denied by Windows. "
                "Move the app out of the Downloads folder to fix this."
            )

        app = ProjectBrowser(settings=settings)
        if single_instance_manager is not None:
            app.single_instance_manager = single_instance_manager
        app.mainloop()
    except Exception:
        logging.getLogger("project_stats").exception("Unhandled application crash")
        raise


if __name__ == "__main__":
    main()
