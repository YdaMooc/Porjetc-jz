"""生成用于界面验证的样本数据（默认 122 项目 / 319 个送样版本）。

真实项目树不便反复折腾时，用它造一份"结构完全合规"的数据来验证界面：
严格按 ProjectService 的解析规则构造 ——
    <主路径>/<年份>/<业务员>/<序号>-<业务员>-<客户编号>-<项目名>-<YYYYMMDD>
项目根目录放一个 0 字节标记文件 "<芯片型号>-<封装>"（get_chip_info 只认 0 字节无扩展名文件）；
送样目录用 "送样"，版本目录名兼容 v1.0-YYYYMMDD 与 v1.0-YYYYMMDD-HHMM 两种写法；
同时在数据目录里写一份 work_time.json（get_project_seconds_bulk 只认规范化后的绝对路径），
这样卡片上的「累计开发时间」也有数据可看，且完全不碰 %LOCALAPPDATA% 下的真实记录。

用法：
    .venv\\Scripts\\python.exe tools\\make_fixture_data.py [主路径]
生成后用 tools/render_main_window.py 的最后一个参数指过去即可，例如：
    .venv\\Scripts\\python.exe tools\\render_main_window.py out.png 1280 800 6000 cards -1 .verify_fixture
"""

import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = WORKSPACE_ROOT / ".verify_fixture"

# 样本数据全部为匿名占位值：只用「结构像真的」来验证界面，
# 不放真实业务员姓名、客户编号、芯片型号与项目名（那是别人的业务数据，不该进仓库）。
SALESMEN = ["业务员A", "业务员B", "业务员C", "业务员D", "业务员E", "业务员F",
            "业务员G", "业务员H", "业务员I", "业务员J", "业务员K"]
CLIENTS = ["K001", "K002", "K003", "K004", "K005", "K006", "K007", "K008", "K009", "K010"]
# 项目名用「项目NN」这种纯占位写法：保留 4~6 字的长度差异（用来验证标题换行与省略号），
# 但不含任何真实产品/设备名称。
NAMES = ["项目01", "项目02", "项目03", "项目04", "项目05", "项目06", "项目07", "项目08",
         "项目09", "项目10", "项目11", "项目12", "项目13", "项目14", "项目15", "项目16",
         "项目17", "项目18", "项目19", "项目20", "项目21", "项目22", "项目23", "项目24",
         "项目25", "项目26", "项目27", "项目28", "项目29", "项目30"]
CHIPS = [("型号A01", "SOP8"), ("型号A02", "SOP8"), ("型号B16", "SOP16"), ("型号B30", "SOP8"),
         ("型号A10", "SOP8"), ("型号B00", "SOP8"), ("型号B21", "SOP16"), ("型号B10", "SOP8"),
         ("型号B21A", "SOP14"), ("型号C00", "QFN32"), ("型号D10", "SOT23-6"), ("型号A00", "SSOP24")]

YEAR_PLAN = ((2024, 12), (2025, 24), (2026, 86))       # 合计 122 个项目
SAMPLES_PLAN = [3] * 85 + [2] * 27 + [1] * 10          # 合计 319 个送样版本


def main() -> int:
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_BASE
    if base.is_dir():
        shutil.rmtree(base)

    rng = random.Random(20260930)
    samples = SAMPLES_PLAN[:]
    rng.shuffle(samples)

    today = date.today().isoformat()
    work_projects: dict[str, dict] = {}
    index = 0
    for year, total in YEAR_PLAN:
        for _ in range(total):
            salesman = SALESMEN[index % len(SALESMEN)]
            client = CLIENTS[index % len(CLIENTS)]
            name = NAMES[index % len(NAMES)]
            chip, package = CHIPS[(index * 5) % len(CHIPS)]
            if index % 7 == 3:
                name = f"{name}-{index:02d}"
            created = date(year, 1 + (index * 5) % 12, 1 + (index * 7) % 27)

            sequence = f"{(index % 40) + 1:03d}"
            folder = f"{sequence}-{salesman}-{client}-{name}-{created.strftime('%Y%m%d')}"
            project_path = base / str(year) / salesman / folder
            project_path.mkdir(parents=True, exist_ok=True)

            # 0 字节标记文件：get_chip_info 用它取芯片型号 + 封装
            (project_path / f"{chip}-{package}").write_text("", encoding="utf-8")

            for version_index in range(samples[index]):
                version_date = created + timedelta(days=version_index * 6)
                stamp = version_date.strftime("%Y%m%d")
                if version_index % 3 == 0:
                    version_name = f"v1.0-{stamp}"                       # 早期备份命名
                else:
                    version_name = f"v1.0-{stamp}-{1400 + version_index * 15 % 100:04d}"
                version_path = project_path / "送样" / version_name
                version_path.mkdir(parents=True, exist_ok=True)
                shot = version_path / f"{salesman}-{client}-{chip}-{package}-{stamp}.png"
                shot.write_bytes(b"\x89PNG\r\n\x1a\n")

            if index % 5 == 0:
                program_dir = project_path / "程序"
                program_dir.mkdir(parents=True, exist_ok=True)
                (program_dir / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

            # 开发时间样本：项目级 days（读取口径同时兼容项目级与版本级）。
            total_seconds = int(((index * 37) % 18 + (0.4 if index % 3 else 0)) * 3600) + (index * 53) % 3600
            today_seconds = int((index * 17) % 3600) if index % 4 == 0 else 0
            days = {"2026-09-20": total_seconds // 3, "2026-09-24": total_seconds // 3}
            if today_seconds:
                days[today] = today_seconds
            work_projects[str(project_path.resolve()).casefold()] = {
                "days": days,
                "versions": {"_total": {"days": {k: v for k, v in days.items() if k != today}}},
            }
            index += 1

    (base / "work_time.json").write_text(
        json.dumps({"schema_version": 1, "projects": work_projects}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print(f"base: {base}")
    print(f"projects={sum(total for _year, total in YEAR_PLAN)} samples={sum(SAMPLES_PLAN)}")
    print(f"salesmen={len(SALESMEN)} chips={len(CHIPS)} work_time_entries={len(work_projects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
