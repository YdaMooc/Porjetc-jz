# 项目统计

本地项目目录的检索与开发工时统计工具（Windows 桌面应用，Tkinter + PyInstaller）。

- **当前版本：1.0.5**（构建日期 2026-10-03）
- 版本号的唯一来源：`project_stats/app_info.py` 里的 `APP_NAME` / `APP_VERSION` / `APP_BUILD_DATE`
- 变更历史见 [`CHANGELOG.md`](CHANGELOG.md)，发布产物与校验见 [`docs/版本管理.md`](docs/版本管理.md)
- 代码仓库：[github.com/YdaMooc/Porjetc-jz](https://github.com/YdaMooc/Porjetc-jz)（`main` 分支；便携版 zip 因体积不入库，用 `tools/make_release.py` 本地生成）

## 功能

- 扫描主路径下的项目目录（约定层级：`主路径\年份\业务员\序号-业务员-客户编号-项目名-立项日期`），解析出项目名、客户编号、芯片型号、封装、脚位、送样次数、立项日期
- 表格视图 / 卡片视图二选一（`Ctrl+1` / `Ctrl+2`，或工具栏分段按钮、工具菜单），支持关键字搜索、多字段筛选、排序
- 自动记录每个项目的开发时间：同一时刻只归属一个项目，带空闲检测与切换宽限期
- 项目统计图：送样次数、业务员、年份、芯片型号、封装分布
- 关闭到系统托盘、单实例运行、低完整性环境自检（启动日志会写明）

## 项目结构

```
project_stats/            主程序源码
├── app.py                入口：单实例判定 → 日志 → 建主窗口
├── app_info.py           应用名 / 版本号 / 构建日期（版本号唯一来源）
├── config/               配置读写（settings_service.py，原子写）
├── models/               数据模型与显示列定义
├── platform/             系统托盘（tray_service.py）
├── runtime/              路径、日志、DPI、空闲检测、单实例、完整性自检
├── services/             目录扫描解析（project_service.py）、开发时间（work_time_service.py）
└── ui/                   主窗口（main_window.py）、主题（theme.py）、自绘控件（widgets.py）
tools/                    辅助脚本（截图、样本数据、版本资源、发布打包）
docs/                     文档：版本管理.md、优化审查报告.md、开发对话总结.md
build.spec                PyInstaller 打包配置（含 Windows 版本资源注入）
portable/dist/            打包输出（工作目录，会被下一次构建替换）
releases/                 正式发布产物：带版本号的 zip + SHA256SUMS.txt + manifest
backups/                  开发过程的源码快照 zip（索引见 backups/README.md）
mockups/                  界面设计稿与实现截图（分「设计稿」「实现截图」两个子目录）
```

## 运行

- 开发运行：`.venv\Scripts\python.exe project_stats\app.py`
- 依赖安装：`pip install -r requirements.txt`（Python 3.14 / Windows x64）

## 数据与配置位置

- 配置与日志：默认跟随程序目录下的 `.project_stats\`；该目录不可写时自动回退到 `%LOCALAPPDATA%\项目统计`
- 开发时间记录：`%LOCALAPPDATA%\项目统计\work_time.json`

## 后台模式

- 「工具 → 设置」里可选关闭窗口时的行为：关闭到系统托盘 / 直接退出
- 关闭到托盘后，通过托盘菜单恢复主窗口或退出程序

## 打包与发布

- 发布（唯一流程）：`.venv\Scripts\python.exe tools\make_release.py`
  先构建到临时目录，成功后再替换 `portable\dist`，并在 `releases\` 生成
  `项目统计_v<版本>_便携版.zip`、源码快照 zip、`SHA256SUMS.txt` 与 `manifest_v<版本>.json`
- 只想重新打包、不重新构建：加 `--no-build`
- 旧的 `build.bat`（先删 `portable\` 再构建，失败会连旧产物一起丢）已于 2026-10-03 **删除**，
  需要时可以从 `backups\` 里任一源码快照 zip 中取回

## 常见问题：日志里出现「Running at low integrity」

如果程序（或整个项目目录）被放在 `Downloads` 这类带**低完整性标签**（Low Mandatory Level）的
目录下，Windows 会强制程序以低完整性运行。此时「打开目录」「双击打开表格」会被系统直接拒绝
（`explorer.exe` 返回 `0xC0000142` / 拒绝访问），启动日志会写：

```
Process integrity: low (0x1000)
WARNING [project_stats] Running at low integrity: opening folders and creating directories outside the app folder will be denied by Windows.
```

修复（一条命令，把该目录的标签恢复成 Medium）：

```powershell
icacls "C:\路径\到\项目目录" /setintegritylevel (OI)(CI)M
```

改完重启程序，日志应变成 `Process integrity: medium (0x2000)`。发布 zip 本身不含标签信息，
从 zip 解压到普通目录不会遇到这个问题。

## 编码约束

本项目源码文件统一使用 UTF-8 编码保存（见 `.editorconfig`，`charset = utf-8`），
不使用 GB2312 或其他本地编码。
