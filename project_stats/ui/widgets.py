"""圆角 + 阴影的自绘控件（Tk 的 ttk 控件做不到圆角，只能画在 Canvas 上）。

这里只放"外观需要自绘、行为要尽量像原生控件"的三个东西：
    RoundedPanel      圆角面板（带柔和阴影），内容放在 .body 里
    RoundedButton     圆角按钮（悬停/按下/禁用状态齐全）
    SegmentedControl  圆角分段控件（视图切换用）
公共参数都从 theme.Theme 取，保证圆角半径、留白、配色全局一致。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from project_stats.runtime.dpi import scaled
from project_stats.ui import theme as th


def rounded_rect_points(x0: float, y0: float, x1: float, y1: float, radius: float) -> list[float]:
    """圆角矩形的控制点：配合 create_polygon(smooth=True) 画出平滑圆角。

    Tk 没有圆角矩形图元；用"每个角放两个控制点 + smooth 样条"是标准做法，
    半径越大拐角越圆，视觉上足够干净。
    """
    radius = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0 + radius, y0,
        x1 - radius, y0,
        x1, y0,
        x1, y0 + radius,
        x1, y1 - radius,
        x1, y1,
        x1 - radius, y1,
        x0 + radius, y1,
        x0, y1,
        x0, y1 - radius,
        x0, y0 + radius,
        x0, y0,
    ]


class RoundedPanel(tk.Canvas):
    """圆角面板。内容放进 `panel.body`。

    两种尺寸模式：
      * 默认：面板跟随父容器（grid sticky="nsew"），内容区同步拉伸；
      * hug=True：面板尺寸跟随内容（信息卡这类高度由内容决定的场景）。
    """

    def __init__(
        self,
        master: tk.Misc,
        theme: th.Theme,
        fill: str = th.PANEL_BG,
        outline: str | None = None,
        radius: int | None = None,
        padding: tuple[int, int] = (0, 0),
        shadow: bool = True,
        page_bg: str = th.APP_BG,
        hug: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(master, background=page_bg, highlightthickness=0, bd=0, takefocus=0, **kwargs)
        # Canvas 默认请求尺寸是 378x265（10c x 7c），会把所在网格撑大；
        # 面板尺寸要么由父容器拉伸、要么由内容决定，所以这里先压到最小。
        self.configure(width=kwargs.get("width", 1), height=kwargs.get("height", 1))
        self.theme = theme
        self._fill = fill
        self._outline = outline
        self._radius = theme.radius_panel if radius is None else radius
        self._shadow = shadow
        self._hug = hug
        self._pad_x, self._pad_y = padding
        self._shadow_pad = theme.shadow_pad if shadow else 0

        self.body = tk.Frame(self, background=fill)
        self._window = self.create_window(0, 0, window=self.body, anchor="nw")
        self.bind("<Configure>", self._on_configure)
        if hug:
            self.body.bind("<Configure>", self._on_body_configure)

    # -------------------------------------------------- 尺寸同步
    def _on_configure(self, event) -> None:
        self._draw(event.width, event.height)

    def _on_body_configure(self, event) -> None:
        width = event.width + 2 * self._pad_x + 2 * self._shadow_pad + 2
        height = event.height + 2 * self._pad_y + 2 * self._shadow_pad + 2
        if (width, height) != (self.winfo_reqwidth(), self.winfo_reqheight()):
            self.configure(width=width, height=height)

    # -------------------------------------------------- 绘制
    def _draw(self, width: int, height: int) -> None:
        pad = self._shadow_pad
        x0, y0 = pad, pad
        x1, y1 = width - pad - 1, height - pad - 1
        if x1 - x0 < 6 or y1 - y0 < 6:
            return

        self.delete("panel")
        if self._shadow:
            for offset, spread, color in self._shadow_layers():
                self.create_polygon(
                    rounded_rect_points(x0 - spread, y0 + offset, x1 + spread, y1 + offset, self._radius),
                    smooth=True, splinesteps=12, fill=color, outline=color, tags="panel",
                )
        self.create_polygon(
            rounded_rect_points(x0, y0, x1, y1, self._radius),
            smooth=True, splinesteps=12,
            fill=self._fill,
            outline=self._outline or self._fill,
            width=1, tags="panel",
        )

        inner_width = max(1, x1 - x0 - 2 * self._pad_x)
        self.coords(self._window, x0 + self._pad_x, y0 + self._pad_y)
        if self._hug:
            self.itemconfigure(self._window, width=inner_width)
        else:
            inner_height = max(1, y1 - y0 - 2 * self._pad_y)
            self.itemconfigure(self._window, width=inner_width, height=inner_height)
        self.tag_raise(self._window)

    def _shadow_layers(self) -> tuple[tuple[int, int, str], ...]:
        scale = self.theme.scale
        return (
            (scaled(3, scale), scaled(1, scale), th.SHADOW_COLORS[0]),
            (scaled(2, scale), 0, th.SHADOW_COLORS[1]),
            (scaled(1, scale), 0, th.SHADOW_COLORS[2]),
        )


class _CanvasButton(tk.Canvas):
    """自绘按钮的共同部分：尺寸、悬停、按下、禁用。"""

    def __init__(self, master: tk.Misc, theme: th.Theme, text: str, font,
                 padding: tuple[int, int], radius: int, page_bg: str,
                 icon: str | None = None, **kwargs) -> None:
        self._text = text
        self._font = font
        self._pad_x, self._pad_y = padding
        self._radius = radius
        self._icon = icon
        self._icon_block = 0
        if icon:
            self._icon_block = int(font.metrics("linespace") * 0.85) + scaled(7, theme.scale)
        natural_width = self._icon_block + font.measure(text) + 2 * padding[0]
        height = font.metrics("linespace") + 2 * padding[1]
        explicit_width = int(kwargs.pop("width", 0) or 0)
        width = explicit_width or natural_width
        super().__init__(master, width=width, height=height, background=page_bg,
                         highlightthickness=0, bd=0, takefocus=0, **kwargs)
        self.theme = theme
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._text_item = self.create_text(width // 2, height // 2, text=text, font=font, anchor="center")
        self._shape_item = self.create_polygon(
            rounded_rect_points(0, 0, width, height, radius), smooth=True, splinesteps=12, tags="shape"
        )
        self.tag_lower(self._shape_item)
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw_icon(self, left: float, center_y: float, color: str) -> None:
        """自绘小图标：目前只有 chart（三根柱子）。

        刻意不用 emoji/图标字体：Tk 首次为 emoji 做字体回退要 300-600 ms，
        而图标字体在不同 Windows 版本上码位也不一致；画布上画几个圆角矩形最稳。
        """
        line = self._font.metrics("linespace")
        size = max(9, int(line * 0.82))
        bar_gap = max(2, size // 5)
        bar_width = max(2, (size - 2 * bar_gap) // 3)
        base = center_y + size / 2
        for index, ratio in enumerate((0.55, 1.0, 0.72)):
            x = left + index * (bar_width + bar_gap)
            top = base - size * ratio
            self.create_polygon(
                rounded_rect_points(x, top, x + bar_width, base, max(1, bar_width / 2)),
                smooth=True, splinesteps=8, fill=color, outline=color, tags="icon",
            )

    # 子类给出配色
    def _colors(self) -> tuple[str, str]:
        raise NotImplementedError

    def _redraw(self) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1 or height <= 1:
            width, height = int(self["width"]), int(self["height"])
        fill, foreground = self._colors()
        self.coords(self._shape_item, *rounded_rect_points(0, 0, width - 1, height - 1, self._radius))
        self.itemconfigure(self._shape_item, fill=fill, outline=fill)
        if self._icon:
            self.delete("icon")
            self._draw_icon(self._pad_x, height / 2, foreground)
            self.coords(self._text_item, self._pad_x + self._icon_block, height / 2)
            self.itemconfigure(self._text_item, anchor="w")
        else:
            self.coords(self._text_item, width // 2, height // 2)
            self.itemconfigure(self._text_item, anchor="center")
        self.itemconfigure(self._text_item, fill=foreground)
        self.tag_raise(self._text_item)

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._update_cursor()
        self._redraw()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._pressed = False
        self._update_cursor()
        self._redraw()

    def _on_press(self, _event) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self._fire_press()

    def _on_release(self, _event) -> None:
        if not self._enabled or not self._pressed:
            self._pressed = False
            return
        self._pressed = False
        self._fire_release()

    def _fire_press(self) -> None:
        self._redraw()

    def _fire_release(self) -> None:
        self._redraw()

    def _update_cursor(self) -> None:
        self.configure(cursor="hand2" if self._enabled and self._hover else "arrow")

    # 兼容 ttk 的调用习惯：configure(state="disabled") / state(["!disabled"])
    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        self._hover = self._hover and enabled
        self._update_cursor()
        self._redraw()

    def configure(self, **kwargs):                     # noqa: D401 - 兼容 ttk 用法
        if "state" in kwargs:
            self.set_enabled(str(kwargs.pop("state")) not in ("disabled", "!normal"))
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            self.itemconfigure(self._text_item, text=self._text)
        return super().configure(**kwargs)

    config = configure

    def state(self, states: Sequence[str] | None = None):
        if states:
            for state in states:
                self.set_enabled(not str(state).startswith("!"))
        return ("disabled",) if not self._enabled else ()


class RoundedButton(_CanvasButton):
    """圆角按钮：primary（实心蓝）/ soft（浅灰）/ ghost（无底色）。"""

    # 每种按钮的状态色都取 theme 里的 token：同一套按钮在工具栏、卡片详情、
    # 统计窗口里出现，颜色必须只有一个来源。
    _KINDS = {
        "primary": (th.ACCENT, "#ffffff", th.ACCENT_HOVER, th.ACCENT_ACTIVE, th.ACCENT_TINT, th.ACCENT_TINT_FG),
        "soft": (th.SURFACE_ALT, th.TEXT_PRIMARY, th.BTN_HOVER, th.BTN_PRESSED, th.SURFACE_ALT, th.TEXT_TERTIARY),
        "ghost": (th.APP_BG, th.TEXT_SECONDARY, th.BTN_GHOST_HOVER, th.BTN_GHOST_PRESSED, th.APP_BG, th.TEXT_TERTIARY),
    }

    def __init__(self, master: tk.Misc, theme: th.Theme, text: str, command: Callable[[], None] | None = None,
                 kind: str = "soft", page_bg: str = th.APP_BG, font=None,
                 padding: tuple[int, int] | None = None, width: int | None = None,
                 icon: str | None = None) -> None:
        font = font or theme.ui
        padding = padding or (scaled(15, theme.scale), scaled(7, theme.scale))
        super().__init__(master, theme, text, font, padding, theme.radius_panel // 2 + 2, page_bg,
                         icon=icon, width=width or 0)
        self._kind = kind if kind in self._KINDS else "soft"
        self._command = command
        if width:
            self.configure(width=width)
            self._redraw()

    def _colors(self) -> tuple[str, str]:
        base, foreground, hover, pressed, disabled_bg, disabled_fg = self._KINDS[self._kind]
        if not self._enabled:
            return disabled_bg, disabled_fg
        if self._pressed:
            return pressed, foreground
        if self._hover:
            return hover, foreground
        return base, foreground

    def _fire_release(self) -> None:
        super()._fire_release()
        if self._command is not None:
            self._command()


class SegmentedControl(tk.Canvas):
    """圆角分段控件：一个凹槽 + 一个滑块 + 若干文字。"""

    def __init__(self, master: tk.Misc, theme: th.Theme, options: Sequence[str],
                 command: Callable[[int], None] | None = None, active: int = 0,
                 page_bg: str = th.APP_BG) -> None:
        self.theme = theme
        # 注意：不能叫 self._options —— 那会覆盖 tkinter.Misc._options()，
        # 控件构造时会报 "'list' object is not callable"。
        self._labels = list(options)
        self._active = max(0, min(active, len(self._labels) - 1))
        self._command = command
        self._hover = -1
        self._pressed = False
        self._font = theme.ui
        pad_x = scaled(14, theme.scale)
        pad_y = scaled(5, theme.scale)
        self._segment_width = max(self._font.measure(option) for option in self._labels) + 2 * pad_x
        self._height = self._font.metrics("linespace") + 2 * pad_y
        self._inset = scaled(2, theme.scale)
        super().__init__(master, width=self._segment_width * len(self._labels) + 2 * self._inset,
                         height=self._height + 2 * self._inset, background=page_bg,
                         highlightthickness=0, bd=0, takefocus=0, cursor="hand2")
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -------------------------------------------------- 交互
    def _index_at(self, x: int) -> int:
        offset = self._inset
        for index in range(len(self._labels)):
            if offset <= x < offset + self._segment_width:
                return index
            offset += self._segment_width
        return -1

    def _on_motion(self, event) -> None:
        index = self._index_at(event.x)
        if index != self._hover:
            self._hover = index
            self._redraw()

    def _on_leave(self, _event) -> None:
        self._hover = -1
        self._pressed = False
        self._redraw()

    def _on_press(self, event) -> None:
        self._pressed = self._index_at(event.x) >= 0

    def _on_release(self, event) -> None:
        index = self._index_at(event.x)
        was_pressed = self._pressed
        self._pressed = False
        if not was_pressed or index < 0:
            return
        self.set_active(index, notify=True)

    def set_active(self, index: int, notify: bool = False) -> None:
        index = max(0, min(index, len(self._labels) - 1))
        changed = index != self._active
        self._active = index
        self._redraw()
        if notify and changed and self._command is not None:
            self._command(index)

    @property
    def active(self) -> int:
        return self._active

    # -------------------------------------------------- 绘制
    def _redraw(self) -> None:
        width = self.winfo_width() or int(self["width"])
        height = self.winfo_height() or int(self["height"])
        inset = self._inset
        self.delete("seg")

        # 凹槽
        self.create_polygon(
            rounded_rect_points(0, 0, width - 1, height - 1, (height - 1) / 2),
            smooth=True, splinesteps=16, fill=th.SEGMENT_TROUGH, outline=th.SEGMENT_TROUGH, tags="seg",
        )
        # 滑块
        left = inset + self._active * self._segment_width
        self.create_polygon(
            rounded_rect_points(left, inset, left + self._segment_width, height - inset,
                                (height - 2 * inset) / 2),
            smooth=True, splinesteps=16, fill=th.PANEL_BG, outline=th.PANEL_BG, tags="seg",
        )
        # 文字
        for index, option in enumerate(self._labels):
            center = inset + index * self._segment_width + self._segment_width / 2
            if index == self._active:
                color = th.TEXT_PRIMARY
            elif index == self._hover:
                color = th.TEXT_PRIMARY
            else:
                color = th.TEXT_SECONDARY
            self.create_text(center, height / 2, text=option, font=self._font, fill=color, tags="seg")


def section_label(master: tk.Misc, theme: th.Theme, text: str, **kwargs) -> ttk.Label:
    """面板里的小节标题：统一字号与颜色，避免每处各写一份。"""
    return ttk.Label(master, text=text, style="CardSection.TLabel", font=theme.section, **kwargs)
