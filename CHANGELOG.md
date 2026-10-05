# 更新日志（CHANGELOG）

「项目统计」的版本变更记录。**本文件从 v1.0.5（2026-10-03）起建立**：在此之前项目没有
任何版本记录文件，`APP_VERSION` 长期停在 `1.0.0`，每批改动的"存档"其实就是 `backups\`
里按阶段命名的源码快照 zip。

- 版本号唯一来源：`project_stats/app_info.py`（`APP_NAME` / `APP_VERSION` / `APP_BUILD_DATE`）
- 发布产物与校验值：`releases\` 目录、[`docs/版本管理.md`](docs/版本管理.md)
- 版本号规则：`主版本.次版本.修订号`，当前处于 1.0.x（同一套界面下的增量维护）

> **关于 v1.0.1 ~ v1.0.4 的编号**：这四个版本号是 2026-10-03 依据 `backups\` 源码快照的
> 时间线**追溯编号**的——当时并没有用这些版本号打过包。它们的作用是把 2026-09-26 ~ 09-30
> 的四批改动分开记账，每条都对应那一批真实存在的源码快照 zip。

## [1.0.8] — 2026-10-05

**数据安全修正**：芯片型号与脚位改为**只读项目根目录的标记文件名**，不再去 `送样`
目录补全封装。

### 背景

v1.0.5 为了把「封装未识别 119/122 → 2/122」，加了 `get_package_hint()`：根标记文件名里
没写封装时，退到 `送样\` 下**送样版本目录名**、再退到**版本目录内的文件名**里去找封装字样。
识别率确实上去了，但代价是程序开始读送样目录里的东西——那里放的是**已经送出去的样品版本**，
任何"顺手读一下"的改动都可能碰到历史送样文件，风险不对等。这项兜底整个移除。

### 变更

- 删除 `ProjectService.get_package_hint()` 与 `_collect_package_hints_from_files()`，
  以及只为它们服务的 `PACKAGE_HINT_FILE_LIMIT = 300`
- `project_service.py` 的 `PACKAGE_PATTERN` 上方写明数据安全约束：
  芯片型号与脚位只允许来自根目录标记文件名，不得读取送样目录内容
- `load_projects()` 不再做封装兜底：标记文件名没写封装就如实留「未设置」
- `ProjectLoadSummary.unresolved_chip_info` 拆成 `unresolved_chip_name` 与
  `unresolved_package` 两个计数，状态栏提示相应改为
  「芯片型号未识别 N 个（根目录无标记文件）」「脚位未识别 N 个（标记文件名没写封装）」

### 影响（实测真实数据 151 个项目）

- 脚位未识别：**4 → 85**。这是这次修正的代价，也是它要解决的问题的性质：
  旧版那 81 个"识别出来"的脚位，全是从送样目录的目录名或文件名里读出来的，
  没有一个是根标记文件写的
- 未识别的 85 个里有 73 个项目**根本没有 `送样` 目录**——对这些项目，旧兜底同样无能为力，
  新旧版都会显示「未设置」
- 项目数、送样次数、筛选与排序、其余字段全部不变；`送样` 目录仍按**名字**统计版本数
  （`count_sample_versions` 只用 `os.scandir` 读目录项名字，不读文件内容、不递归、不写入）
- 筛选下拉里的「未设置」正好用来找出这 85 个项目，方便人工确认脚位

### 验证

- 抽一个具体项目对照：脚位由 `SOP16`（旧版从送样文件名里认出来的）变为「未设置」，
  芯片型号与送样次数均不变
- 全量加载 151 个项目：`unresolved_chip_name=1`、`unresolved_package=85`、脚位候选 8 个
- 用一次性的旧逻辑复刻脚本对比出上面的 4 → 85（脚本已删）
- 实现截图改用真实数据（151 项目 / 408 送样）重拍，图里能直接看到「脚位」有值 /
  「未设置」两种状态（该截图目录已于 1.0.9 移出仓库）
- `compileall project_stats` 通过

## [1.0.7] — 2026-10-05

界面配色改为柔和现代色板。**只换颜色，不动布局**：控件位置、尺寸、文字、筛选与排序逻辑
全部保持原样，逐屏截图核对过内容没有丢失。

### 变更

- `project_stats\ui\theme.py` 的配色段整体重写，确立四条规则写在文件顶部：
  中性色统一带蓝紫色相（约 225°）、强调色只用于「可点 / 已选中 / 数字」、
  不用纯黑与满饱和色、同一颜色全仓只允许一个定义
- 主色由亮蓝 `#0a6ff0` 改为低饱和靛蓝 `#4a6cf0`，并按「常态 / 悬停 / 按下」补成三档
  （删掉旧常量 `ACCENT_DARK`，改为 `ACCENT_HOVER` `#3a58d4` 与 `ACCENT_ACTIVE` `#3350c0`）
- 中性色整体降对比：页面底色 `#eef0f5 → #f4f6fa`、分隔线 `#e6e8ef → #eceef4`、
  正文 `#1b1c20 → #23252f`、次要文字 `#6b6e7a → #666c7e`、三级文字 `#989ba6 → #9aa0af`
- 卡片阴影明显减弱（`SHADOW_COLORS` `#d7d9e4/#e4e6ef/#eff1f7 → #e2e5ef/#ebedf5/#f3f5fa`），
  卡片靠底色差浮起来，而不是靠明显的投影
- 图表配色接入主题：网格线 `CHART_GRID` `#ebeef5`、悬停选中的柱子 `CHART_SELECTED` `#4fae84`，
  柱体用 `ACCENT`
- **收敛散落的硬编码色**：按钮 / 滚动条 / 标签页 / 分段控件里的 `#bcd6fb` `#f2f7ff` `#d3d6e2`
  `#bfc3d4` `#aeb3c7` `#e7e9f1` `#eef0f6` `#e7e9f0` 等 14 处字面值全部改为主题常量，
  新增 `SEGMENT_TROUGH` / `BTN_HOVER` / `BTN_PRESSED` / `BTN_GHOST_HOVER` / `BTN_GHOST_PRESSED` /
  `SCROLL_THUMB*` / `TAB_BG` / `TAB_HOVER` / `CHART_GRID` / `CHART_SELECTED` /
  `ACCENT_TINT` / `ACCENT_TINT_FG` / `PURPLE` 等具名 token
- 概览条四个数字各用一个颜色：项目 `ACCENT`、送样 `SUCCESS`、业务员 `WARNING`、芯片 `PURPLE`

### 明确不做的项

- 不改用 QML 重写：本项目的技术栈是 Tkinter/ttk + 自绘圆角控件，
  配色属于主题层改动，换工具包会把 2700 行的主窗口全部推倒重来，收益与风险不成比例
- 不改系统托盘图标配色（`project_stats\platform\tray_service.py` 的 `#007aff/#34c759/#ff9f0a`）：
  那是应用在系统托盘里的品牌色，与窗口内的色板不是一回事

### 验证

- `tools\render_main_window.py` 新增子窗口截图能力（第 8 个参数 `settings|stats|new`），
  用于逐屏核对
- 抓图方式由抓屏（`ImageGrab`）改为 `PrintWindow`：本机环境下被主窗口遮住的子窗口
  在抓屏里根本拍不到（`GetWindowRect` / `IsWindowVisible` 都正常也不行，试过
  `-topmost`、`lift()`、`SetWindowPos` 抬 z 序均无效），改成让窗口自己往内存 DC
  重画一遍才稳定；代价是对话框丢了系统投影，图里对话框外圈有一圈黑边
- 122 项目 / 319 送样样本数据下逐屏截图：卡片视图、卡片展开、表格视图、设置窗口、
  统计窗口、新增项目对话框均确认文字、数字、按钮、滚动条完整
- `mockups\实现截图\美化_*.png` 5 张按新配色重拍（原先的截图是 v1.0.4 ~ v1.0.5 的样子）

---

## [1.0.7.1] — 2026-10-05

开发工具修正（**不影响程序本体**，`project_stats\` 本次未改动）。

### 修正

- `tools\render_main_window.py` 截图 `stats` 目标时进程永不退出（表现为"卡死"）：
  统计子窗口里的 `plt.subplots()` 走 pyplot，matplotlib 的 TkAgg 后端会**另建一个隐藏的
  Tk 主窗口**（`matplotlib/backends/_backend_tk.py` 的 `FigureManagerTk.create_with_canvas`：
  `window = tk.Tk(className="matplotlib"); window.withdraw()`），而 `tkinter` 的 `mainloop()`
  要等进程里所有 Tk 主窗口都销毁才返回——只 `app.destroy()` 的话，图早已存盘、命令却永远挂在
  `app.mainloop()` 上（stdout 走管道时还是块缓冲，连一行打印都看不到）
- 修法：截图存盘后走新的 `shutdown()`，先 `plt.close("all")` 拆掉那个隐藏主窗口再
  `app.destroy()`；用 `"matplotlib.pyplot" in sys.modules` 判断，保证非绘图分支行为不变
- 效果：`stats` 目标由「永不返回」变为 **11.6s / EXIT=0**，`main` 目标仍 10.8s / EXIT=0
- 顺带纠正上文一句：`stats` 截图慢**不是** matplotlib 初始化慢，`_load_chart_modules()` 只需
  0.77s；此前把它记成"已知问题"是误判

---

## [1.0.6] — 2026-10-03

主界面信息架构优化，按新版渲染稿落地：

- 新增顶部概览条，实时显示当前筛选结果的项目数、送样数、业务员数和芯片数
- 表格视图移除重复的信息卡，详情栏扩大可用高度并将列表与详情比例调整为约 68:32
- 新增 `Ctrl+K` 快速聚焦搜索框，并保留 `Ctrl+1` / `Ctrl+2` 视图切换
- 卡片视图与表格视图共用同一组概览数据，避免统计数字在不同视图间跳动
- 目录加载增加 15 秒超时保护，失联网络盘不会永久锁住界面；仿真脚本在创建窗口前禁用上次路径自动恢复
- 保持原有路径、筛选、搜索、排序、详情、统计和托盘流程不变

---

## [1.0.5] — 2026-10-03

工程规范化与首次编号发布。**二进制功能与 2026-09-30 构建的便携版一致**，差别在版本元数据、
依赖清理与文档。

### 新增

- **Windows 版本资源**：`build.spec` 通过新增的 `tools/version_info.py` 把版本号写进 exe，
  「属性 → 详细信息」里首次能看到文件版本 / 产品版本 / 产品名称（此前这四个字段全是空的）
- **`tools/make_release.py`**：安全发布脚本——先构建到临时目录，成功后才替换 `portable\dist`，
  失败时上一版产物原样保留；同时生成带版本号的便携版 zip、源码快照 zip、
  `releases\SHA256SUMS.txt` 与 `manifest_v<版本>.json`
- **`requirements.txt`**：首次固定依赖版本（此前只能从 `.venv` 里反查）
- **`CHANGELOG.md` / `docs\版本管理.md`**：变更记录与版本管理规范
- **`releases\`**：正式发布产物目录
- 便携版 zip 顶层新增包裹目录「项目统计」，解压后不会散落文件

### 变更

- `APP_VERSION`：1.0.0 → 1.0.5，新增 `APP_BUILD_DATE = "2026-10-03"`
- 「关于」对话框显示「版本：1.0.5（2026-10-03）」
- `README.md`：GBK → UTF-8（全仓最后一个非 UTF-8 文本文件），并更正内容——
  原文写的 `build.ps1` 早已不存在、打包输出目录实际是 `portable\dist\`

### 修复

- 清理 `.venv` 里的第三方同名包 `project_stats 2.0.0`（github.com/xi/project-stats，GPLv2+）：
  它与本项目的包**同名**，会让 PyInstaller 的模块分析出现歧义、并把一个 GPLv2+ 的无关包拖进依赖图；
  卸载后重新打包，新旧 bundle 顶层 82 个条目**完全一致**——`yaml` 仍在包内，它来自
  `numpy\__config__.py` 的 `import yaml`，`dateutil` 则来自 matplotlib 自带的 hook，都与该包无关

### 已知问题（本版未处理，见 `docs\优化审查报告.md`）

- `work_time_service.py` 遇到损坏的 `work_time.json` 会静默归零，没有隔离备份
- 60 秒刷新会整表重建；`_fit_columns_to_width` 仍有重复调用点（已加宽度守卫）
- `project_stats\platform\` 与标准库 `platform` 同名，靠导入顺序规避

### 仓库整理（2026-10-03，发布后）

- 根目录只留 `README.md` / `CHANGELOG.md` / `requirements.txt` / `build.spec` / `.editorconfig` /
  `项目统计.ico`；把 `版本管理.md`、`优化审查报告.md`、`开发对话总结.md` 移进新建的 `docs\`
- 删除 `build.bat`：它是「先删 `portable\` 再构建」的老流程（构建失败会连旧产物一起丢），
  已被 `tools\make_release.py` 完全取代；14 个 `backups\` 源码快照里都留有副本，可随时取回
- 删除 2026-09-30 及更早的重复产物：`portable_fixed\`（09-30 00:57 构建，早于低完整性修复）、
  `portable\build\`、`portable\dist_上一版_20261003_162018\`、`portable\项目统计_便携版\`（解压副本）、
  `portable\项目统计_便携版.zip`（与 `releases\项目统计_v1.0.5_便携版.zip` 内容完全重复）
- 删除两个空临时目录（`tmpjkfnn9e9`、`tmpwxctodl3`）与全部 `__pycache__`；共释放约 375 MB，
  `portable\` 现在只剩 `dist\`（当前构建）
- `backups\` 14 个源码快照**全部保留**并新增 `README.md` 索引（zip ↔ 版本 ↔ 内容对照）；
  `mockups\` 拆成 `设计稿\`（23 张）与 `实现截图\`（9 张）并新增 `README.md`
- `tools\make_release.py`：源码清单改指 `docs\…`、不再复制那份无版本号的便携版 zip、
  每次构建只保留最近一版 `dist_上一版_*`（旧的自动清理）

### 发布验证

- 便携版冒烟：直接运行 `portable\dist\项目统计\项目统计.exe`，窗口标题为「项目统计 1.0.5」，
  日志写入 `.project_stats\logs\project_stats.log`（首行 `Starting 项目统计 1.0.5`）
- 本项目目录 2026-10-03 **又被打上了低完整性标签**（日志 `Process integrity: low (0x1000)`，
  此时「打开目录」会被 Windows 拒绝）。已用 `icacls "…\项目统计" /setintegritylevel (OI)(CI)M`
  恢复，复测为 `Process integrity: medium (0x2000)`；排查步骤写进 `README.md` 常见问题一节
- 发布 zip 不含 ACL/完整性标签，从 zip 解压到普通目录不受此问题影响

### 源码快照

- `releases\项目统计_v1.0.5_source.zip`（含 `MANIFEST.txt` 与每个文件的 SHA256）

---

## [1.0.4] — 2026-09-30

界面美化与效率优化。对应源码快照：`backups\项目统计_source_美化前_20260930_013612.zip`（改前）。

### 新增

- `project_stats\ui\theme.py`：配色、字体、ttk 样式集中管理
- `project_stats\ui\widgets.py`：Tk 没有圆角，改用自绘 `RoundedPanel`（圆角面板 + 柔和阴影）、
  `RoundedButton`（悬停/按下/禁用）、`SegmentedControl`（圆角分段控件）
- `project_stats\runtime\dpi.py`：DPI 感知（必须在建 Tk 根窗口之前调用）

### 变更

- 字体统一到中文字形完整的 **Microsoft YaHei UI**：原来到处硬编码 `("Segoe UI", …)`，
  而 Segoe UI 没有中文字形，中文逐字回退造成同行字重、字宽、行高不齐
- Tk 命名字体一并替换，覆盖 messagebox、下拉列表等系统控件；统计图的中文字体也改为优先用主题字体

### 性能

- 去掉 `📊`（U+1F4CA）：它首次排版要枚举系统字体做缺字回退，一次性 350–620 ms，
  冷启动到窗口可见 **1393 ms → 447–502 ms**（占冷启动 60% 以上）
- `_normalize_path` 改走 `os.path.normcase(os.path.abspath())` 快路径：
  151 条真实路径 31.07 ms → 0.143 ms（**216.6×**，逐条比对 0 条结果不一致）
- 表格列宽测量加「宽度未变即返回」守卫

### 修复

- **`main_window.py` 导入即崩**：第 20 行调用 `dpi.enable_dpi_awareness()`，而
  `from project_stats.runtime import dpi` 在第 54 行 → `NameError: name 'dpi' is not defined`
- `SegmentedControl` 的 `self._options` 覆盖了 `tkinter.Misc._options()` → 控件构造报错（改名 `self._labels`）
- 换字体后表格列宽截断（`K00123456` 显示成 `K0012345(`），改为按真实字体测量最小列宽
- 画布默认请求尺寸 378×265 把右栏网格撑高，改为 `configure(width=1, height=1)`

### 明确不做的项（有实测依据）

- 表格批量填充改写：151 行 `tree.insert` 只要 1.2–1.9 ms，「480 ms」的前提不成立，9 种写法差异 ≤5 ms
- 卡片墙虚拟化：只省约 31 ms，却要给 5 处状态同步加分支，并把零成本滚动变成每次重画，
  盈亏平衡点约 1500 张卡
- pystray / PIL 延迟导入：省约 50 ms，但会改变托盘图标的出现时机

---

## [1.0.3] — 2026-09-29 ~ 09-30

卡片视图（方案 E）与卡片化布局定稿。
源码快照：`backups\项目统计_source_卡片布局定稿_20260929_005055.zip`、
`backups\项目统计_source_卡片视图前_20260930_010943.zip`（改前）。

### 新增

- **卡片视图**：整墙画在一张 Canvas 上（一张卡 = 1 个矩形 + 3 段文字），与表格视图占用同一个
  grid 格二选一显示；卡片视图下右栏收起、统计数字移到状态栏右侧
- 视图切换：工具栏分段按钮、工具菜单、`Ctrl+1` / `Ctrl+2`
- 卡内展开详情：详情是真实的 Frame，用 canvas window 摆进卡片内部，并按实测高度撑高该行
- 卡片排序下拉：最近立项 / 项目名称 / 送样次数 / 累计开发时间
- 配置项 `view_mode`（老配置缺字段自动补默认值，非法值同样退回默认）
- `WorkTimeService.get_project_seconds_bulk()`：一次批量取工时，替代逐个项目单查
- `tools\make_fixture_data.py`：按解析规则生成合规样本数据（122 项目 / 319 送样）
- `tools\render_main_window.py` 重写：可指定尺寸、等待时间、视图、展开第几张卡，且**不写回**用户配置

### 性能

- 首次建墙 151 张卡：**1222 ms → 190 ms**（6.4×）
- 任一筛选 / 排序：300–800 ms → 16–92 ms（约 10×）
- 60 秒工时刷新：约 150 ms → 39 ms
- 切回卡片视图：407 ms → 129 ms

### 修复

- 展开卡里第三个按钮被截断 → 改成主操作占满一行、两个次操作平分下一行
- 详情区高度算小了，压到下一行且浮在卡片外面 → 改为画在卡片内部并按实测高度撑高

---

## [1.0.2] — 2026-09-27

主界面 D2 改版 + 开发时间计时规则改造 + 设置窗口改版。
源码快照：计时改造前/后、设置窗口改造后、主界面改造前/后、主界面 D2 完成/定稿共 7 个 zip
（`backups\项目统计_source_*_20260927_*.zip`）。

### 新增

- 主界面按 D2 稿重排：行 0 工具栏（主路径 + 浏览 / 读取项目 / 新增项目 / 项目统计 / 设置），
  行 1 左栏（筛选 + 关键字搜索 + 列表）与右栏（顶部信息卡 + 项目详情）并列，行 2 状态栏
- 右栏拆成「信息卡 + 项目详情」两张独立卡片，列表也包进卡片
- **开发时间计时规则改造**：互斥归属（同一时刻只归属一个项目）+ 观察期 + 空闲检测，
  设置项 `idle_timeout_seconds = 180`、`active_window_seconds = 600`、`switch_grace_seconds = 120`；
  同一份数据下总工时 **257.67 h → 238.87 h（−18.80 h，−7.3%）**，即旧口径把空闲时间与
  多项目并发时间重复计入了
- 设置窗口改版（标签页布局）

### 修复

- 窗口请求宽度 1287px 超出 1366×768 屏幕被裁 → 列宽按权重自适应，默认窗口 1180×700
- 序号被 trace 回调重复追加（`"001"` → `"001001"`）
- 列宽被旧逻辑覆盖（每列强制 min 80px）、横向滚动条常驻

---

## [1.0.1] — 2026-09-26

第一批优化（可靠性 + 性能 + 解析准确性）与应用更名。
源码快照：`backups\项目统计_source_20260926_131834.zip`（改前）、
`backups\项目统计_source_改后_20260926_141325.zip`（改后）。

### 变更

- 应用名「项目文件浏览器」→ **「项目统计」**：此前 exe、托盘、README 都叫"项目统计"，
  只有程序内部（含日志首行 `Starting 项目文件浏览器 1.0.0`）还是旧名
- 窗口标题、托盘标题统一带上版本号

### 性能

- 启动 **1317 ms → 205 ms**：matplotlib / pyplot / mplcursors 改为在统计图窗口里延迟导入
  （其中 `import pyplot` 独占 634 ms）
- 主线程阻塞 **361 ms → 0.3 ms**：工时基线扫描移到后台线程，完成后回主线程刷新

### 修复

- 配置保存改为原子写（临时文件 + `replace`），失败只记 warning
- 程序目录不可写时回退 `%LOCALAPPDATA%\项目统计`（原来放在只读位置会直接启动失败）
- 单实例：删掉语义错误的 `ReleaseMutex`、第二实例先 `CloseHandle`、互斥体名改为含安装路径哈希的
  `Local\ProjectStats_<路径哈希>`
- 单实例判定提前到建窗之前（否则第二个实例会先读配置、先建 UI，甚至回写 `settings.json`）
- 送样目录版本正则兼容 `v1.0-YYYYMMDD`（无时分）这种早期命名：**292 → 319（+27）**
- 封装识别放宽根文件命名规则：**未识别 119/122 → 2/122**
  （SOP8 66、SOT23-6 21、SOP16 17、SOP14 15、TSSOP20 1）
- 后台线程 `after()` 在窗口销毁后抛 `RuntimeError: main thread is not in main loop`
  （原来只捕获 `tk.TclError`）
- 用 `os.path.isdir()` 替代 `exists()`，避免对文件路径调列表接口报
  `NotADirectoryError [WinError 267]`
- 工时保存失败不再让计时线程静默停更（连续 3 次失败才停，并写日志）
- 更正一处早期错误结论：含「副本 / copy」的送样目录**本来就被正确排除**，
  原结论错在复核脚本用了 `re.search` 而不是 `fullmatch`

---

## [1.0.0] — 2026-09-05

首个可运行版本（历史版本，无发布产物留存）。

- 项目目录扫描、表格列表、关键字搜索与多字段筛选、统计图（matplotlib）、
  开发时间记录、系统托盘、设置窗口、单实例运行
- 应用名「项目文件浏览器」，`APP_VERSION = "1.0.0"`
- 无 Windows 版本资源、无依赖清单、无变更记录
- 源码快照：`backups\项目统计_source_20260905_023335.zip`（33 个文件，含现已废弃的 `build.ps1`）
