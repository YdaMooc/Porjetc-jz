"""开发期截图工具：启动窗口、载入数据、把窗口渲染成 png 后退出。

仅用于把当前实现渲染成图片，与 mockups/ 下的设计稿做 1:1 比对。
用法：
    .venv\\Scripts\\python.exe tools\\render_main_window.py <输出png> [宽 高] [等待毫秒] [视图 cards|table] [展开第几张卡] [主路径] [窗口 main|settings|stats|new] [开发时间记录文件]
说明：
    视图参数直接改内存里的 _view_mode，不走 set_view_mode()；
    指定主路径时也不会把路径写进用户配置（_save_settings 被临时替换），
    避免"截图"这个动作改掉用户的上次视图 / 上次路径。
    窗口参数（第 8 个）用于截子窗口：settings / stats / new 会弹出对应子窗口，
    按主窗口相对坐标贴到主窗口截图之上，得到与真实观感一致的合成图。
    第 8 个参数写成路径时按旧用法当开发时间记录文件，第 9 个参数仍是记录文件
    （两种写法都保留，避免历史命令失效）。

关于抓图方式（踩过的坑，别改回去）：
    ImageGrab.grab() 走桌面 DC 的 BitBlt，只能拿到真正合成到桌面上的像素。
    这台机器上被遮挡的 Tk 子窗口（设置/新增/统计对话框）即使 GetWindowRect 与
    IsWindowVisible 都正常，抓屏里也完全没有它——试过 -topmost、lift()、
    SetWindowPos 抬 z 序、撤掉主窗口 topmost，全部无效。所以改成 PrintWindow：
    让窗口自己往内存 DC 重画一遍，不依赖桌面合成结果，也不受遮挡影响。
    PrintWindow 不会画窗口投影，对话框边缘因此没有阴影，这是可接受的。

关于退出前必须关掉 pyplot（踩过的坑，别改回去）：
    matplotlib 的 TkAgg 后端在 pyplot 建图时（statistics 子窗口的 plt.subplots）会
    另外新建一个隐藏的 tk.Tk(className="matplotlib") 主窗口，见
    matplotlib/backends/_backend_tk.py 里 FigureManagerTk.create_with_canvas 的
    `window = tk.Tk(className="matplotlib")`。tkinter 的 mainloop() 要等进程里所有
    Tk 主窗口都销毁才返回，所以只 app.destroy() 的话：图已经存盘、PrintWindow 也已执行，
    但 mainloop() 永远不返回，命令挂死（stdout 是块缓冲时连一行打印都看不到）。
    必须先 plt.close("all") 把那个隐藏主窗口一起拆掉，再 destroy 主窗口。
"""

import ctypes
import ctypes.wintypes
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from PIL import Image, ImageGrab  # noqa: E402

from project_stats.services.work_time_service import WorkTimeService  # noqa: E402
from project_stats.config import SettingsService  # noqa: E402
from project_stats.ui.main_window import ProjectBrowser  # noqa: E402


USER32 = ctypes.windll.user32
GDI32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.wintypes.DWORD),
        ("biWidth", ctypes.wintypes.LONG),
        ("biHeight", ctypes.wintypes.LONG),
        ("biPlanes", ctypes.wintypes.WORD),
        ("biBitCount", ctypes.wintypes.WORD),
        ("biCompression", ctypes.wintypes.DWORD),
        ("biSizeImage", ctypes.wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.wintypes.LONG),
        ("biYPelsPerMeter", ctypes.wintypes.LONG),
        ("biClrUsed", ctypes.wintypes.DWORD),
        ("biClrImportant", ctypes.wintypes.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", ctypes.wintypes.DWORD * 3)]


def widget_hwnd(widget: object) -> int:
    """取 Tk 窗口真正的顶层 HWND（winfo_id() 给的是内容窗口，上一层才是）。"""
    inner = widget.winfo_id()
    return USER32.GetParent(inner) or inner


def window_rect(widget: object) -> tuple[int, int, int, int]:
    rect = ctypes.wintypes.RECT()
    USER32.GetWindowRect(widget_hwnd(widget), ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def client_offsets(widget: object) -> tuple[int, int]:
    """内容区（客户区）相对整窗左上角的偏移，也就是边框 + 标题栏的厚度。

    PrintWindow 拍的是带边框的整窗，而 Tk 的 winfo_rootx/rooty 指的是内容区左上角；
    两者差这份偏移，合成与裁剪都要用它对齐，否则会整体错开几像素。
    """
    left, top, _, _ = window_rect(widget)
    return widget.winfo_rootx() - left, widget.winfo_rooty() - top


def capture_window(widget: object) -> Image.Image:
    """用 PrintWindow 把窗口画到内存 DC 再取成 PIL 图，含窗口边框与标题栏。"""
    hwnd = widget_hwnd(widget)
    left, top, right, bottom = window_rect(widget)
    width, height = right - left, bottom - top
    hdc_window = USER32.GetWindowDC(hwnd)
    hdc_memory = GDI32.CreateCompatibleDC(hdc_window)
    hbitmap = GDI32.CreateCompatibleBitmap(hdc_window, width, height)
    GDI32.SelectObject(hdc_memory, hbitmap)
    try:
        USER32.PrintWindow(hwnd, hdc_memory, PW_RENDERFULLCONTENT)
        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height          # 负数 = 自上而下，省一次翻转
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        buffer = ctypes.create_string_buffer(width * height * 4)
        GDI32.GetDIBits(hdc_memory, hbitmap, 0, height, buffer,
                        ctypes.byref(info), DIB_RGB_COLORS)
        return Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        GDI32.DeleteObject(hbitmap)
        GDI32.DeleteDC(hdc_memory)
        USER32.ReleaseDC(hwnd, hdc_window)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help", "/?"}:
        print(__doc__)
        return 0
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "render.png").resolve()
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1180
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 760
    delay_ms = int(sys.argv[4]) if len(sys.argv) > 4 else 3500
    view_mode = sys.argv[5].strip().lower() if len(sys.argv) > 5 else ""
    expand_index = int(sys.argv[6]) if len(sys.argv) > 6 else -1
    base_path = sys.argv[7].strip() if len(sys.argv) > 7 else ""
    target = ""          # 第 8 个参数：main|settings|stats|new，留空等于 main
    work_time_file = ""  # 第 9 个参数：仅样本验证用
    if len(sys.argv) > 8:
        eighth = sys.argv[8].strip()
        if eighth.lower() in {"main", "settings", "stats", "new"}:
            target = eighth.lower()
        else:
            # 旧用法里第 8 个位置放的是开发时间记录文件，保持兼容
            work_time_file = eighth
    if len(sys.argv) > 9:
        work_time_file = sys.argv[9].strip()

    if work_time_file:
        # 只有显式给出时才替换开发时间记录文件（样本验证用）；
        # 否则一律沿用 %LOCALAPPDATA% 下的真实记录，绝不往数据目录里写。
        storage = Path(work_time_file).resolve()
        WorkTimeService.default_storage_path = staticmethod(lambda: storage)

    # 必须在构造窗口前禁用自动恢复上次路径；ProjectBrowser 会在构造阶段
    # 安排自动加载，等创建完成后再改 settings 已经太晚，可能同时扫描失联网络盘。
    launch_settings = SettingsService().load()
    if base_path or work_time_file:
        launch_settings.auto_load_last_path = False
        launch_settings.auto_track_work_time = False
    app = ProjectBrowser(settings=launch_settings)
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

    def place_dialog(min_width: int = 520, min_height: int = 360) -> object:
        """把刚弹出的子窗口摆到主窗口内的固定位置，返回它。

        只负责「摆位」，不再负责「抬到最前」：抓图已经改成 PrintWindow，
        子窗口被主窗口盖住也照样能拍出来（详见模块 docstring 里的坑）。
        摆位本身仍有必要——否则窗口管理器会把子窗口居中甚至放到屏幕外，
        合成到主窗口图上时会跑到画面外去。
        """
        app.update_idletasks()
        app.update()
        dialog = next(
            (child for child in app.winfo_children() if child.winfo_class() == "Toplevel"),
            None,
        )
        if dialog is None:
            print("warning: 没有找到子窗口")
            return None
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        want_w = min(max(dialog.winfo_reqwidth(), min_width), screen_w - 80)
        want_h = min(max(dialog.winfo_reqheight(), min_height), screen_h - 120)
        pos_x = min(max(app.winfo_rootx() + 40, 20), screen_w - want_w - 20)
        pos_y = min(max(app.winfo_rooty() + 28, 20), screen_h - want_h - 20)
        dialog.deiconify()
        # 单次 geometry() 会被 transient/grab_set 跳过（实测停在 +0+0），
        # 必须配合 lift() 多来几次才真正落位。
        for _ in range(4):
            dialog.geometry(f"{want_w}x{want_h}+{pos_x}+{pos_y}")
            dialog.lift()
            dialog.update_idletasks()
            dialog.update()
        app.update()
        print(f"dialog: {dialog.winfo_geometry()} "
              f"root=({dialog.winfo_rootx()},{dialog.winfo_rooty()}) "
              f"want=({want_w}x{want_h}+{pos_x}+{pos_y})")
        return dialog

    def shoot() -> None:
        if 0 <= expand_index < len(app._card_layout):
            app._select_card(app._card_layout[expand_index]["path"], expand=True)
            app.update_idletasks()
            app.update()
        if target == "settings":
            app.show_settings()
            app._dialog = place_dialog()
        elif target == "stats":
            app.show_statistics()
            app._dialog = place_dialog(760, 620)
        elif target == "new":
            app.show_new_project()
            app._dialog = place_dialog()
        for _ in range(8):
            app.update_idletasks()
            app.update()
        app.after(700, grab)

    def grab() -> None:
        app.update_idletasks()
        app.update()
        cards = len(app._card_layout)
        columns = app._card_columns
        selected = app._selected_path or "-"
        print(f"target={target} view={app._view_mode} cards={cards} columns={columns}")
        print(f"selected: {selected}")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        app_left, app_top, _, _ = window_rect(app)
        app_inset_x, app_inset_y = client_offsets(app)
        window_image = capture_window(app)
        print(f"app window: {window_image.width}x{window_image.height} at ({app_left},{app_top}) "
              f"client inset=({app_inset_x},{app_inset_y})")

        dialog = getattr(app, "_dialog", None)
        if dialog is not None:
            dialog_image = capture_window(dialog)
            # 对话框按内容区左上角对齐贴到主窗口内容区上：两个窗口都各去掉自己的
            # 边框/标题栏厚度，剩下的就是内容区之间的相对位移。
            dialog_inset_x, dialog_inset_y = client_offsets(dialog)
            offset_x = (dialog.winfo_rootx() - app.winfo_rootx()) + (app_inset_x - dialog_inset_x)
            offset_y = (dialog.winfo_rooty() - app.winfo_rooty()) + (app_inset_y - dialog_inset_y)
            window_image.paste(dialog_image, (offset_x, offset_y))
            dialog_path = out_path.with_name(out_path.stem + "_dialog.png")
            dialog_image.save(dialog_path)
            print(f"dialog pasted at ({offset_x},{offset_y}): "
                  f"{dialog_image.width}x{dialog_image.height}")
            print(f"saved dialog: {dialog_path}")

        # 裁成「主窗口内容区」那一块：内容区起点就是边框厚度，尺寸用请求的宽高。
        image = window_image.crop(
            (app_inset_x, app_inset_y, app_inset_x + width, app_inset_y + height)
        )
        image.save(out_path)
        print(f"saved: {out_path} ({image.width}x{image.height})")
        app.after(100, shutdown)

    def shutdown() -> None:
        """截图存盘后退出：必须先拆掉 matplotlib 那个隐藏的 Tk 主窗口。

        pyplot 建 figure（统计子窗口里的 plt.subplots）时，TkAgg 后端会另建一个隐藏的
        tk.Tk(className="matplotlib") 主窗口，见 matplotlib/backends/_backend_tk.py 里
        FigureManagerTk.create_with_canvas。而 tkinter 的 mainloop() 要等进程里所有 Tk
        主窗口都销毁才返回——只 app.destroy() 的话，图已经存盘、命令却会永远挂在
        后面的 app.mainloop() 里（stdout 走管道时还是块缓冲，连一行打印都看不到）。
        plt.close("all") 会连带把那个隐藏主窗口一起销毁。
        """
        if "matplotlib.pyplot" in sys.modules:
            import matplotlib.pyplot as plt

            plt.close("all")
        app.destroy()

    app.after(delay_ms, shoot)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
