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
# 页面灰 → 白色面板 → 面板内浅色块，三级层次；边框比之前淡，靠留白和阴影分层。
APP_BG = "#eef0f5"            # 页面底色
PANEL_BG = "#ffffff"          # 卡片/面板
SURFACE_ALT = "#f6f7fa"       # 面板内的次级块（字段区、路径区）
SURFACE_SUNKEN = "#f2f3f8"    # 更浅的凹陷块（信息条）
LINE = "#e6e8ef"              # 常规分隔线
LINE_STRONG = "#d9dce6"       # 需要更明确边界时
TEXT_PRIMARY = "#1b1c20"
TEXT_SECONDARY = "#6b6e7a"
TEXT_TERTIARY = "#989ba6"
ACCENT = "#0a6ff0"
ACCENT_DARK = "#0059cc"
ACCENT_SOFT = "#e9f2ff"
SUCCESS = "#2fa36b"
WARNING = "#e08a1e"
ROW_NORMAL = "#ffffff"
ROW_ALT = "#fafbfd"
ROW_SELECTED = "#e7f0ff"
ROW_HOVER = "#f2f7ff"
WALL_BG = "#f3f4f8"           # 卡片墙底色：比卡片略深，卡片才"浮"得起来
SHADOW_COLORS = ("#d7d9e4", "#e4e6ef", "#eff1f7")   # 由深到浅，模拟羽化
SHADOW_STRONG = ("#c8cbdd", "#daddec", "#e7e9f4")   # 悬停/选中时用，卡片"浮"起来

# 卡片墙配色（Canvas 绘制）
CARD_HOVER_BG = "#ffffff"
CARD_HOVER_BORDER = "#b7c8e6"
DETAIL_BOX_BG = "#f4f5f9"

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
    _flat_button(style, "TButton", SURFACE_ALT, TEXT_PRIMARY, "#e9ebf3", "#e2e5ef",
                 SURFACE_ALT, TEXT_TERTIARY, (pad_x, pad_y))
    _flat_button(style, "Primary.TButton", ACCENT, "#ffffff", ACCENT_DARK, ACCENT_DARK,
                 "#bcd6fb", "#f2f7ff", (pad_x, pad_y))
    _flat_button(style, "Soft.TButton", SURFACE_ALT, TEXT_PRIMARY, "#e9ebf3", "#e2e5ef",
                 SURFACE_ALT, TEXT_TERTIARY, (pad_x, pad_y))
    _flat_button(style, "Ghost.TButton", APP_BG, TEXT_SECONDARY, "#e6e9f1", "#dfe3ed",
                 APP_BG, TEXT_TERTIARY, (compact_x, compact_y))
    _flat_button(style, "CompactPrimary.TButton", ACCENT, "#ffffff", ACCENT_DARK, ACCENT_DARK,
                 "#bcd6fb", "#f2f7ff", (compact_x, compact_y))
    _flat_button(style, "CompactSoft.TButton", SURFACE_ALT, TEXT_PRIMARY, "#e9ebf3", "#e2e5ef",
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
            background="#d3d6e2",
            troughcolor=PANEL_BG,
            bordercolor=PANEL_BG,
            lightcolor="#d3d6e2",
            darkcolor="#d3d6e2",
            arrowcolor=PANEL_BG,
            relief="flat",
        )
        style.map(name, background=[("active", "#bfc3d4"), ("pressed", "#aeb3c7")])

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
        background="#e7e9f1",
        foreground=TEXT_SECONDARY,
        borderwidth=0,
        font=theme.ui,
    )
    style.map(
        "Settings.TNotebook.Tab",
        background=[("selected", PANEL_BG), ("active", "#eef0f6")],
        foreground=[("selected", TEXT_PRIMARY)],
        expand=[("selected", (0, 0, 0, 0))],
    )
    return style
