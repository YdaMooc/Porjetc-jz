"""临时截图工具：启动主窗口、载入数据、截取窗口区域后退出。

仅用于开发期把当前实现渲染成图片，与 mockups/ 下的设计稿做 1:1 比对。
用法：
    .venv\\Scripts\\python.exe tools\\render_main_window.py <输出png> [宽 高] [等待毫秒] [视图 cards|table] [展开第几张卡] [主路径]
说明：
    视图参数直接改内存里的 _view_mode，不走 set_view_mode()；
    指定主路径时也不会把路径写进用户配置（_save_settings 被临时替换），
    避免“截图”这个动作改掉用户的上次视图 / 上次路径。
"""

import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from PIL import ImageGrab  # noqa: E402

from project_stats.services.work_time_service import WorkTimeService  # noqa: E402
from project_stats.ui.main_window import ProjectBrowser  # noqa: E402


def main() -> int:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "render.png").resolve()
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1180
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 760
    delay_ms = int(sys.argv[4]) if len(sys.argv) > 4 else 3500
    view_mode = sys.argv[5].strip().lower() if len(sys.argv) > 5 else ""
    expand_index = int(sys.argv[6]) if len(sys.argv) > 6 else -1
    base_path = sys.argv[7].strip() if len(sys.argv) > 7 else ""
    work_time_file = sys.argv[8].strip() if len(sys.argv) > 8 else ""

    if work_time_file:
        # 只有显式给出时才替换开发时间记录文件（样本验证用）；
        # 否则一律沿用 %LOCALAPPDATA% 下的真实记录，绝不往数据目录里写。
        storage = Path(work_time_file).resolve()
        WorkTimeService.default_storage_path = staticmethod(lambda: storage)

    app = ProjectBrowser()
    app.geometry(f"{width}x{height}+60+40")
    if view_mode in {"cards", "table"}:
        app._view_mode = view_mode
        app._apply_view_mode()
    if base_path or work_time_file:
        app._save_settings = lambda: None      # 截图不改用户配置
        app.settings.auto_load_last_path = False
        app.settings.auto_track_work_time = False
        app.work_time_service.set_enabled(False)   # 也不要在真实数据上计时
    if base_path:
        app.path_var.set(str(Path(base_path).resolve()))
        app.load_projects(notify_on_complete=False)

    def shoot() -> None:
        app.lift()
        app.attributes("-topmost", True)
        app.update_idletasks()
        app.update()
        if 0 <= expand_index < len(app._card_layout):
            app._select_card(app._card_layout[expand_index]["path"], expand=True)
            app.update_idletasks()
            app.update()
        app.after(400, grab)

    def grab() -> None:
        app.update_idletasks()
        x = app.winfo_rootx()
        y = app.winfo_rooty()
        w = app.winfo_width()
        h = app.winfo_height()
        cards = len(app._card_layout)
        columns = app._card_columns
        selected = app._selected_path or "-"
        print(f"view={app._view_mode} cards={cards} columns={columns}")
        print(f"selected: {selected}")
        print(f"window geometry: {w}x{h} at ({x},{y})")
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
        print(f"saved: {out_path} ({image.width}x{image.height})")
        app.after(100, app.destroy)

    app.after(delay_ms, shoot)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
