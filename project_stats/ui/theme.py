"""主界面主题：配色、字体、ttk 样式。

为什么单独一个模块：Tk 的 ttk 主题是一堆散落的 style.configure 调用，
和业务代码混在一起很容易出现"某个控件忘了配背景色"这类破绽；集中在这里，
主界面只负责布局与交互。

字体策略：Tk 默认字体本来就是 Microsoft YaHei UI（CJK 完整），但界面代码里
硬编码了 ("Segoe UI", …) —— Segoe UI 没有中文字形，中文只能逐字回退到别的
字体，于是同一行里字重、字宽、行高都不一致。这里统一走一个"中文字形完整"的
家族（按可用性回退），并把 Tk 的命名字体一起改掉，保证 messagebox、下拉列表
这些系统控件也跟着变。

Tk 不支持圆角与阴影（ttk 控件都是矩形），需要圆角的面板统一用
`project_stats.ui.widgets.RoundedPanel` 画在 Canvas 上。
"""

from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

from project_stats.runtime.dpi import scaled


# ----------------------------------------------------------------- 配色
# 一套"柔和现代"的色板：低饱和的冷灰骨架 + 一个收敛的靛蓝强调色。
#
# 三条规则，改配色时照着走就不会跑偏：
#   1. 中性色都带一点蓝紫（色相 225° 上下），不掺暖黄灰——暖灰和冷灰混用是
#      旧版看起来"发脏"的主要原因；
#   2. 强调色只用于"可点/已选中/数字"，其余层次全靠留白、圆角和极淡的阴影区分，
#      不靠对比强烈的边框；
#   3. 不用纯黑（#000）和满饱和的高亮色：正文用 #23252f，彩色一律压到中等明度。
#   4. 同一个颜色（比如强调色的按下态）只允许有一个定义，任何地方需要"更深一点的靛蓝"
#      都从这里取，不再就地写 #3f5fd0 之类的临时值。
#
# 层次自下而上：APP_BG（页面）→ WALL_BG（卡片墙）→ PANEL_BG（面板/卡片）→ SURFACE_ALT。
# 相邻两层只差 2~4 个明度台阶，面板靠阴影"浮"起来，而不是靠描边。
APP_BG = "#f4f6fa"            # 页面底色
PANEL_BG = "#ffffff"          # 卡片/面板
SURFACE_ALT = "#f7f8fb"       # 面板内的次级块（字段区、路径区）
SURFACE_SUNKEN = "#f2f4f8"    # 更浅的凹陷块（信息条）
LINE = "#eceef4"              # 常规分隔线（比旧版淡一档，边界不强加）
LINE_STRONG = "#dde1eb"       # 需要更明确边界时（输入框描边）
TEXT_PRIMARY = "#23252f"
TEXT_SECONDARY = "#666c7e"
TEXT_TERTIARY = "#9aa0af"
ACCENT = "#4a6cf0"            # 靛蓝：比旧版 #0a6ff0 低饱和，长时间看不刺眼
ACCENT_HOVER = "#3a58d4"      # 悬停：比常态深一档
ACCENT_ACTIVE = "#3350c0"     # 按下：再深一档
ACCENT_SOFT = "#ecf0fe"       # 浅底（选中项、菜单高亮）
ACCENT_TINT = "#93a9f6"       # 主按钮禁用态底色（浅靛蓝）
ACCENT_TINT_FG = "#eef1fd"    # 主按钮禁用态文字（同色系白，禁用要看得出来但仍可读）
SUCCESS = "#3f9e73"           # 成功/累计（偏灰的绿，不抢眼）
WARNING = "#cc8a3d"           # 提醒/送样
PURPLE = "#8a72d9"            # 第四个数据维度的点缀色（芯片数）
ROW_NORMAL = "#ffffff"
ROW_ALT = "#fafbfe"           # 隔行底色：冷白，比旧版的暖白更适合表格
ROW_SELECTED = "#e9eefe"
ROW_HOVER = "#f4f7fe"
WALL_BG = "#f2f4f9"           # 卡片墙底色：比卡片略深，卡片才"浮"得起来
SHADOW_COLORS = ("#e2e5ef", "#ebedf5", "#f3f5fa")   # 由深到浅，模拟羽化
SHADOW_STRONG = ("#d3d8e6", "#dfe3ee", "#eaedf6")   # 悬停/选中时用，卡片"浮"起来

# 卡片墙配色（Canvas 绘制）
CARD_HOVER_BG = "#ffffff"
CARD_HOVER_BORDER = "#c3d0f2"     # 悬停描边：淡靛蓝，只做提示不做分割
DETAIL_BOX_BG = "#f5f7fc"

# 自绘控件与 ttk 细节色（集中在这里，避免同一种"悬停灰"在多处各写一遍）
SEGMENT_TROUGH = "#e5e8f1"        # 分段控件凹槽
BTN_HOVER = "#e9ecf6"             # 浅灰按钮悬停
BTN_PRESSED = "#e0e4f2"           # 浅灰按钮按下
BTN_GHOST_HOVER = "#e8ebf4"       # 无底色按钮悬停（页面底色上）
BTN_GHOST_PRESSED = "#dfe3f0"
SCROLL_THUMB = "#ced3e0"
SCROLL_THUMB_HOVER = "#b8bfd1"
SCROLL_THUMB_PRESSED = "#a5adc2"
TAB_BG = "#e8eaf3"                # 未选中的标签页
TAB_HOVER = "#eef1f9"
CHART_GRID = "#ebeef5"            # 统计图表网格线
CHART_SELECTED = "#4fae84"        # 图表里被悬停选中的柱子（比 SUCCESS 亮一点才看得出来）

# 兼容旧名（统计窗口等处仍沿用）
APP_BG_LEGACY = APP_BG

FONT_FAMILY_CANDIDATES = (
    "Microsoft YaHei UI",     # Windows 8+ 中文界面字体，CJK 完整、字重齐全
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Segoe UI",
    "Tahoma",
)
FALLBACK_FAMILY = "TkDefaultFont"

# 字号（磅；96 DPI 下 1pt ≈ 1.33px）
SIZE_UI = 9
SIZE_SECTION = 10
SIZE_CARD_TITLE = 11
SIZE_SMALL = 8
SIZE_METRIC = 17
SIZE_METRIC_SMALL = 12

NAMED_FONTS = (
    "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
    "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
)


@dataclass(frozen=True)
class Theme:
    """字体 + 像素度量。像素度量已按 DPI 缩放取整。"""

    scale: float
    family: str
    ui: tkfont.Font
    ui_bold: tkfont.Font
    section: tkfont.Font
    card_title: tkfont.Font
    card_body: tkfont.Font
    small: tkfont.Font
    metric: tkfont.Font
    metric_small: tkfont.Font
    # 面板与卡片
    radius_panel: int
    radius_card: int
    shadow_pad: int
    card_pad: int
    card_gap: int
    card_min_width: int
    card_height: int
    card_title_block: int
    card_meta_block: int
    card_detail_min: int
    # 表格
    row_height: int
    heading_pad: int
    scrollbar_width: int
    # 窗口
    window_size: tuple[int, int]
    window_min: tuple[int, int]


def resolve_family(root) -> str:
    """挑一个中文字形完整的家族；一个都没有时退回 Tk 默认。"""
    try:
        available = set(tkfont.families(root))
    except Exception:                                     # pragma: no cover - 极端环境
        return "TkDefaultFont"
    for family in FONT_FAMILY_CANDIDATES:
        if family in available:
            return family
    try:
        return tkfont.nametofont("TkDefaultFont").actual("family")
    except Exception:                                     # pragma: no cover
        return "Tahoma"


def _named_font(root, name: str, family: str, size: int, weight: str = "normal") -> tkfont.Font:
    try:
        font = tkfont.nametofont(name)
        font.configure(family=family, size=size, weight=weight)
        return font
    except Exception:                                     # pragma: no cover
        try:
            return tkfont.Font(root=root, name=name, family=family, size=size, weight=weight)
        except Exception:
            return tkfont.Font(root=root, family=family, size=size, weight=weight)


def create_theme(root, scale: float = 1.0) -> Theme:
    family = resolve_family(root)

    # Tk 自己的命名字体（对话框、菜单、下拉列表都用它们）一起换掉，
    # 否则 messagebox 会比主界面"换了一种字体"。
    for name in NAMED_FONTS:
        try:
            tkfont.nametofont(name).configure(family=family, size=SIZE_UI)
        except Exception:                                 # pragma: no cover
            pass

    ui = _named_font(root, "AppUI", family, SIZE_UI)
    ui_bold = _named_font(root, "AppUIBold", family, SIZE_UI, "bold")
    section = _named_font(root, "AppSection", family, SIZE_SECTION, "bold")
    card_title = _named_font(root, "AppCardTitle", family, SIZE_CARD_TITLE, "bold")
    card_body = _named_font(root, "AppCardBody", family, SIZE_UI)
    small = _named_font(root, "AppSmall", family, SIZE_SMALL)
    metric = _named_font(root, "AppMetric", family, SIZE_METRIC, "bold")
    metric_small = _named_font(root, "AppMetricSmall", family, SIZE_METRIC_SMALL, "bold")

    ui_line = ui.metrics("linespace")
    body_line = card_body.metrics("linespace")
    title_line = card_title.metrics("linespace")

    card_pad = scaled(13, scale)
    title_block = title_line * 2 + scaled(2, scale)       # 标题固定按两行预留
    meta_block = body_line + scaled(3, scale)
    card_height = card_pad * 2 + title_block + meta_block + body_line * 4 + scaled(4, scale)

    return Theme(
        scale=scale,
        family=family,
        ui=ui,
        ui_bold=ui_bold,
        section=section,
        card_title=card_title,
        card_body=card_body,
        small=small,
        metric=metric,
        metric_small=metric_small,
        radius_panel=scaled(12, scale),
        radius_card=scaled(10, scale),
        shadow_pad=scaled(5, scale),
        card_pad=card_pad,
        card_gap=scaled(12, scale),
        card_min_width=scaled(262, scale),
        card_height=card_height,
        card_title_block=title_block,
        card_meta_block=meta_block,
        card_detail_min=scaled(104, scale),
        row_height=max(scaled(26, scale), ui_line + scaled(11, scale)),
        heading_pad=scaled(8, scale),
        scrollbar_width=scaled(10, scale),
        window_size=(scaled(1240, scale), scaled(760, scale)),
        window_min=(scaled(1040, scale), scaled(640, scale)),
    )


# ----------------------------------------------------------------- ttk 样式


def _flat_button(style: ttk.Style, name: str, background: str, foreground: str,
                 active: str, pressed: str, disabled_bg: str, disabled_fg: str,
                 padding: tuple[int, int]) -> None:
    """平面按钮：去掉浮雕与虚线焦点框（焦点框颜色设成背景色即不可见）。"""
    style.configure(
        name,
        background=background,
        foreground=foreground,
        borderwidth=0,
        relief="flat",
        padding=padding,
        focuscolor=background,
        focusthickness=0,
        anchor="center",
    )
    style.map(
        name,
        background=[("disabled", disabled_bg), ("pressed", pressed), ("active", active)],
        foreground=[("disabled", disabled_fg)],
    )


def apply_ttk_theme(root, theme: Theme) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")          # clam 最容易改色，其它主题很多选项不生效
    except Exception:                                     # pragma: no cover
        pass

    pad_x = scaled(15, theme.scale)
    pad_y = scaled(8, theme.scale)
    compact_x = scaled(11, theme.scale)
    compact_y = scaled(5, theme.scale)

    # ---------- 基础容器与文字
    style.configure(".", font=theme.ui, background=APP_BG, foreground=TEXT_PRIMARY)
    style.configure("TFrame", background=APP_BG)
    style.configure("Band.TFrame", background=APP_BG)
    style.configure("Surface.TFrame", background=PANEL_BG)
    style.configure("Card.TFrame", background=PANEL_BG)
    style.configure("Detail.TFrame", background=PANEL_BG)
    style.configure("Metric.TFrame", background=PANEL_BG)
    style.configure("WorkTime.TFrame", background=SURFACE_ALT)
    style.configure("DetailPath.TFrame", background=SURFACE_ALT)

    for name, background, foreground, font in (
        ("TLabel", APP_BG, TEXT_PRIMARY, theme.ui),
        ("Band.TLabel", APP_BG, TEXT_PRIMARY, theme.ui),
        ("Muted.TLabel", APP_BG, TEXT_SECONDARY, theme.ui),
        ("Section.TLabel", APP_BG, TEXT_SECONDARY, theme.section),
        ("Panel.TLabel", PANEL_BG, TEXT_PRIMARY, theme.ui),
        ("PanelMuted.TLabel", PANEL_BG, TEXT_SECONDARY, theme.ui),
        ("PanelSection.TLabel", PANEL_BG, TEXT_PRIMARY, theme.section),
        ("Card.TLabel", PANEL_BG, TEXT_PRIMARY, theme.ui),
        ("CardMuted.TLabel", PANEL_BG, TEXT_SECONDARY, theme.ui),
        ("CardSection.TLabel", PANEL_BG, TEXT_PRIMARY, theme.section),
        ("Detail.TLabel", PANEL_BG, TEXT_TERTIARY, theme.ui),
        ("DetailValue.TLabel", PANEL_BG, TEXT_PRIMARY, theme.ui),
        ("DetailSection.TLabel", PANEL_BG, TEXT_PRIMARY, theme.section),
        ("MetricLabel.TLabel", PANEL_BG, TEXT_SECONDARY, theme.small),
        ("MetricValue.TLabel", PANEL_BG, TEXT_PRIMARY, theme.metric),
        ("WorkTimeLabel.TLabel", SURFACE_ALT, TEXT_SECONDARY, theme.ui),
        ("WorkTimeToday.TLabel", SURFACE_ALT, ACCENT, theme.metric_small),
        ("WorkTimeTotal.TLabel", SURFACE_ALT, SUCCESS, theme.metric_small),
        ("DetailPathLabel.TLabel", SURFACE_ALT, TEXT_TERTIARY, theme.small),
        ("DetailPathValue.TLabel", SURFACE_ALT, TEXT_SECONDARY, theme.small),
        ("Status.TLabel", PANEL_BG, TEXT_TERTIARY, theme.small),
        ("EmptyState.TLabel", PANEL_BG, TEXT_TERTIARY, theme.ui),
    ):
        style.configure(name, background=background, foreground=foreground, font=font)

    for name, background in (
        ("Panel.TSeparator", LINE),
        ("Card.TSeparator", LINE),
        ("Detail.TSeparator", LINE),
    ):
        style.configure(name, background=background)

    # ---------- 按钮
    # 浅灰按钮的三种状态只在"底色略深一点"之间走，不做描边/阴影，和卡片一样的扁平语言。
    _flat_button(style, "TButton", SURFACE_ALT, TEXT_PRIMARY, BTN_HOVER, BTN_PRESSED,
                 SURFACE_ALT, TEXT_TERTIARY, (pad_x, pad_y))
    _flat_button(style, "Primary.TButton", ACCENT, "#ffffff", ACCENT_HOVER, ACCENT_ACTIVE,
                 ACCENT_TINT, ACCENT_TINT_FG, (pad_x, pad_y))
    _flat_button(style, "Soft.TButton", SURFACE_ALT, TEXT_PRIMARY, BTN_HOVER, BTN_PRESSED,
                 SURFACE_ALT, TEXT_TERTIARY, (pad_x, pad_y))
    _flat_button(style, "Ghost.TButton", APP_BG, TEXT_SECONDARY, BTN_GHOST_HOVER, BTN_GHOST_PRESSED,
                 APP_BG, TEXT_TERTIARY, (compact_x, compact_y))
    _flat_button(style, "CompactPrimary.TButton", ACCENT, "#ffffff", ACCENT_HOVER, ACCENT_ACTIVE,
                 ACCENT_TINT, ACCENT_TINT_FG, (compact_x, compact_y))
    _flat_button(style, "CompactSoft.TButton", SURFACE_ALT, TEXT_PRIMARY, BTN_HOVER, BTN_PRESSED,
                 SURFACE_ALT, TEXT_TERTIARY, (compact_x, compact_y))

    # ---------- 输入类
    style.configure(
        "TEntry",
        fieldbackground=PANEL_BG,
        foreground=TEXT_PRIMARY,
        insertcolor=ACCENT,
        bordercolor=LINE_STRONG,
        lightcolor=LINE_STRONG,
        darkcolor=LINE_STRONG,
        padding=scaled(7, theme.scale),
        relief="flat",
    )
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)])

    style.configure(
        "TCombobox",
        fieldbackground=PANEL_BG,
        background=PANEL_BG,
        foreground=TEXT_PRIMARY,
        bordercolor=LINE_STRONG,
        lightcolor=LINE_STRONG,
        darkcolor=LINE_STRONG,
        arrowcolor=TEXT_SECONDARY,
        padding=(scaled(6, theme.scale), scaled(3, theme.scale)),
        relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", PANEL_BG), ("disabled", SURFACE_ALT)],
        foreground=[("readonly", TEXT_PRIMARY), ("disabled", TEXT_TERTIARY)],
        bordercolor=[("focus", ACCENT), ("hover", LINE_STRONG)],
        arrowcolor=[("disabled", TEXT_TERTIARY)],
    )
    # 下拉弹出列表是原生 Listbox，只能用 option database 改
    root.option_add("*TCombobox*Listbox.background", PANEL_BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.font", theme.ui)

    style.configure("TCheckbutton", background=PANEL_BG, foreground=TEXT_PRIMARY, focuscolor=PANEL_BG)
    style.map("TCheckbutton", background=[("active", PANEL_BG)],
              indicatorcolor=[("selected", ACCENT), ("!selected", PANEL_BG)])
    style.configure("TRadiobutton", background=PANEL_BG, foreground=TEXT_PRIMARY, focuscolor=PANEL_BG)
    style.map("TRadiobutton", background=[("active", PANEL_BG)])

    # ---------- 表格
    style.configure(
        "Project.Treeview",
        background=ROW_NORMAL,
        fieldbackground=ROW_NORMAL,
        foreground=TEXT_PRIMARY,
        rowheight=theme.row_height,
        borderwidth=0,
        relief="flat",
        font=theme.ui,
    )
    style.layout("Project.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])   # 去掉外框
    style.configure(
        "Project.Treeview.Heading",
        background=PANEL_BG,
        foreground=TEXT_SECONDARY,
        relief="flat",
        borderwidth=0,
        font=theme.ui_bold,
        padding=(theme.heading_pad, theme.heading_pad + scaled(2, theme.scale)),
    )
    style.map(
        "Project.Treeview.Heading",
        background=[("active", SURFACE_ALT)],
        foreground=[("active", TEXT_PRIMARY)],
        relief=[("active", "flat")],
    )
    style.map(
        "Project.Treeview",
        background=[("selected", ROW_SELECTED)],
        foreground=[("selected", TEXT_PRIMARY)],
    )

    # ---------- 滚动条：细、无箭头
    for orient, prefix in (("vertical", "Vertical"), ("horizontal", "Horizontal")):
        name = f"Slim.{prefix}.TScrollbar"
        style.layout(name, [
            (f"{prefix}.Scrollbar.trough", {
                "sticky": "ns" if orient == "vertical" else "ew",
                "children": [(f"{prefix}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
            })
        ])
        style.configure(
            name,
            width=theme.scrollbar_width,
            background=SCROLL_THUMB,
            troughcolor=PANEL_BG,
            bordercolor=PANEL_BG,
            lightcolor=SCROLL_THUMB,
            darkcolor=SCROLL_THUMB,
            arrowcolor=PANEL_BG,
            relief="flat",
        )
        style.map(name, background=[("active", SCROLL_THUMB_HOVER), ("pressed", SCROLL_THUMB_PRESSED)])

    # 旧名字（旧代码里还有引用）指到同一套样式
    for prefix in ("Vertical", "Horizontal"):
        for target in (f"{prefix}.TScrollbar", f"Project.{prefix}.TScrollbar"):
            style.layout(target, style.layout(f"Slim.{prefix}.TScrollbar"))
            for option in ("width", "background", "troughcolor", "bordercolor",
                           "lightcolor", "darkcolor", "arrowcolor", "relief"):
                style.configure(target, **{option: style.lookup(f"Slim.{prefix}.TScrollbar", option)})
            style.map(target, background=style.map(f"Slim.{prefix}.TScrollbar", "background"))

    # ---------- 设置窗口的标签页
    style.configure("Settings.TNotebook", background=APP_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(
        "Settings.TNotebook.Tab",
        padding=(scaled(18, theme.scale), scaled(7, theme.scale)),
        background=TAB_BG,
        foreground=TEXT_SECONDARY,
        borderwidth=0,
        font=theme.ui,
    )
    style.map(
        "Settings.TNotebook.Tab",
        background=[("selected", PANEL_BG), ("active", TAB_HOVER)],
        foreground=[("selected", TEXT_PRIMARY)],
        expand=[("selected", (0, 0, 0, 0))],
    )
    return style
