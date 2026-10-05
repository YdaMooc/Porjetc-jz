import os
import re
import stat
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from project_stats.models import ProjectRecord


ALL_OPTION = "\u5168\u90e8"
UNSET_OPTION = "\u672a\u8bbe\u7f6e"
SEARCH_FULL_PROJECT_NAME = "\u9879\u76ee\u5168\u79f0"
SEARCH_SALESMAN = "\u4e1a\u52a1\u5458"
SEARCH_CLIENT = "\u5ba2\u6237\u7f16\u53f7"
SEARCH_PROJECT_NAME = "\u9879\u76ee\u540d\u79f0"
SEARCH_CHIP_NAME = "\u82af\u7247\u578b\u53f7"
SEARCH_PACKAGE = "\u811a\u4f4d"
STAT_SALESMAN = "\u4e1a\u52a1\u5458"
STAT_CHIP_NAME = "\u82af\u7247\u578b\u53f7"

PACKAGE_NAME_PATTERN = (
    r"(?:SOP|SSOP|TSSOP|MSOP|SOIC|DIP|QFN|DFN|LQFP|QFP|BGA|SOT|TO)"
    r"\d+(?:-\d+(?![\dA-Za-z]))?"       # SOP8 / SOT23-6：允许 -6 这类脚位数
    r"|(?P<bare>SOP|SOIC|DIP|QFN|DFN|QFP)(?=-\d)"  # SOP-8 / XYZ-SOIC-8：连字符写法统一输出 SOP / SOIC
)
# 只用来解析「项目根目录的 0 字节无扩展名标记文件」这一个名字。
# 不用 $ 锚定：真实标记文件形如 型号A01-SOP8、型号B21-SOT23-6、ABC-QFN32(4x4)、HX-SOP16A，
# 封装名后常带额外后缀。命名语义由 _split_chip_and_package() 负责，这里只负责"找出封装字样"。
#
# 【数据安全约束】芯片型号与脚位只允许来自根目录的标记文件名。
# 不要去读「送样」及其子目录——那里放的是已经送出去的样品版本，只允许按名字统计版本数
# （count_sample_versions），不允许为了补全字段去读它的目录名或文件名：
# 一旦读取范围扩到送样目录，任何"顺手读一下"的改动都可能碰到历史送样文件，风险不对等。
PACKAGE_PATTERN = re.compile(PACKAGE_NAME_PATTERN, re.IGNORECASE)
PACKAGE_TAIL_PATTERN = re.compile(
    rf"[-_\s]*(?P<pkg>{PACKAGE_NAME_PATTERN})(?![\dA-Za-z])(?:[-_\s(].*)?$",
    re.IGNORECASE,
)
SAMPLE_DIR_NAME = "\u9001\u6837"
SAMPLE_VERSION_PATTERN = re.compile(
    # 兼容两种送样版本目录命名：
    #   规范命名：v1.0-20260926-1510（日期后带时间/描述）
    #   早期备份：v1.0-20260926      （日期后没有内容，属未规范的历史目录，同样计入）
    # (?!\d) 保证日期恰好 8 位，避免把 ...-202512010-... 这类 9 位数字误当日期。
    r"^v\d+(?:\.\d+)*[-_\s]+(?P<date>\d{8})(?!\d)(?:[-_\s].*)?$",
    re.IGNORECASE,
)
SAMPLE_COPY_MARKERS = ("\u526f\u672c", "copy")
DATE_SUFFIX_PATTERN = re.compile(
    r"^(?P<prefix>.*?)[-_\s]+"
    r"(?P<year>\d{4})(?:[-_.年]?)"
    r"(?P<month>\d{1,2})(?:[-_.月]?)"
    r"(?P<day>\d{1,2})日?$"
)
SEARCH_FIELD_MAP = {
    SEARCH_FULL_PROJECT_NAME: "full_project_name",
    SEARCH_SALESMAN: "salesman",
    SEARCH_PROJECT_NAME: "project_name",
    SEARCH_CLIENT: "client",
    SEARCH_CHIP_NAME: "chip_name",
    SEARCH_PACKAGE: "package_name",
}
DEFAULT_SEARCH_FIELDS = list(SEARCH_FIELD_MAP)
STAT_FIELD_MAP = {
    STAT_SALESMAN: "salesman",
    STAT_CHIP_NAME: "chip_name",
}


def _is_ascii_year(value: str) -> bool:
    """只接受 ASCII 数字年份，避免全角数字目录被误识别。"""
    return len(value) == 4 and all("0" <= char <= "9" for char in value)


@dataclass(slots=True)
class ProjectLoadSummary:
    # 这些计数不是业务数据，只是给界面一个“加载时发生了什么”的可见反馈。
    invalid_project_folders: int = 0
    unresolved_chip_name: int = 0
    unresolved_package: int = 0
    unreadable_directories: int = 0


@dataclass(slots=True)
class ProjectCatalog:
    projects: list[ProjectRecord]
    years: list[str]
    salesmen: list[str]
    clients: list[str]
    chips: list[str]
    packages: list[str]
    load_summary: ProjectLoadSummary = field(default_factory=ProjectLoadSummary)


class ProjectService:
    def parse_project_folder(self, folder_name: str) -> tuple[str, str, str, str] | None:
        date_parts = self._split_date_suffix(folder_name)
        if date_parts is None:
            return None

        name_without_date, created_date = date_parts
        parts = [part.strip() for part in name_without_date.split("-")]
        if len(parts) < 4 or not parts[0] or not parts[2]:
            return None

        project_name = "-".join(parts[3:]).strip()
        if not project_name:
            return None

        sequence = parts[0]
        client = parts[2]
        return sequence, client, project_name, created_date

    def _split_date_suffix(self, folder_name: str) -> tuple[str, str] | None:
        match = DATE_SUFFIX_PATTERN.match(folder_name.strip())
        if not match:
            return None

        created_date = self._normalize_date(
            match.group("year"),
            match.group("month"),
            match.group("day"),
        )
        if created_date is None:
            return None

        name_without_date = match.group("prefix").strip().rstrip("-_ .")
        if not name_without_date:
            return None

        return name_without_date, created_date

    @staticmethod
    def _normalize_date(year_text: str, month_text: str, day_text: str) -> str | None:
        try:
            parsed_date = date(int(year_text), int(month_text), int(day_text))
        except ValueError:
            return None
        return parsed_date.isoformat()

    def get_chip_info(self, project_path: str) -> tuple[str, str]:
        try:
            fallback_chip_name = UNSET_OPTION
            # 目录枚举先排序，避免 os.listdir 的顺序不稳定导致同一目录解析结果漂移。
            for entry in sorted(os.listdir(project_path)):
                entry_path = os.path.join(project_path, entry)
                try:
                    # 不能只用 os.path.isfile：目录联接(junction)在 os.path.isdir 下为 False，
                    # 却会通过 isfile 判定。这里用 stat 只认"普通文件"。
                    if not stat.S_ISREG(os.stat(entry_path).st_mode):
                        continue
                    if os.path.getsize(entry_path) != 0:
                        continue
                except OSError:
                    continue

                if os.path.splitext(entry)[1]:
                    continue

                chip_name, package_name = self._split_chip_and_package(entry.strip())
                if package_name != UNSET_OPTION:
                    return chip_name, package_name
                if fallback_chip_name == UNSET_OPTION:
                    fallback_chip_name = chip_name
        except OSError:
            return UNSET_OPTION, UNSET_OPTION

        if fallback_chip_name != UNSET_OPTION:
            return fallback_chip_name, UNSET_OPTION

        return UNSET_OPTION, UNSET_OPTION

    @staticmethod
    def _split_chip_and_package(entry: str) -> tuple[str, str]:
        # 从标记文件名里拆出"芯片型号 + 封装"。
        # 先按"封装在结尾"处理（型号A01-SOP8），这样芯片名最干净；
        # 结尾对不上时退而求其次，取文件名里最后一处封装字样（HX-SOP16A）。
        for match in (PACKAGE_TAIL_PATTERN.search(entry), *PACKAGE_PATTERN.finditer(entry)):
            if match is None:
                continue
            # 尾部模式用了命名组（前面可能带分隔符），finditer 的结果整体就是封装名。
            groups = match.groupdict()
            package_name = groups.get("pkg") or groups.get("bare") or match.group(0)
            chip_name = entry[:match.start()].rstrip("-_ ").strip()
            if chip_name:
                return chip_name, package_name.upper()
            if match.start() > 0:
                # 前面还有内容但都是分隔符，例如 " -SOP8"
                return entry.strip(), UNSET_OPTION

        # 整串就是一个封装名（如 MSOP8）：按老行为当作"只有芯片名、封装未设置"，
        # 不要把封装名同时当成芯片型号，否则筛选下拉里会出现只叫 SOP8 的"芯片"。
        if PACKAGE_PATTERN.fullmatch(entry):
            return entry, UNSET_OPTION

        return entry, UNSET_OPTION

    # ------------------------------------------------------------ 新增项目辅助

    def parse_project_identity(self, text: str) -> tuple[str, str, str, str] | None:
        """解析粘贴进“项目名称”的完整片段。

        支持：
        - ``业务员-客户编号-项目名-YYYYMMDD``
        - ``序号-业务员-客户编号-项目名-YYYYMMDD``

        返回业务员、客户编号、纯项目名和标准日期；普通项目名则返回 ``None``，
        这样用户仍可以自由输入不带前缀的名称。
        """
        date_parts = self._split_date_suffix(text.strip())
        if date_parts is None:
            return None
        name_without_date, created_date = date_parts
        parts = [part.strip() for part in name_without_date.split("-")]
        if parts and parts[0].isdigit() and len(parts) >= 4:
            parts = parts[1:]
        if len(parts) < 3 or not parts[0] or not parts[1]:
            return None
        project_name = "-".join(parts[2:]).strip()
        if not project_name:
            return None
        return parts[0], parts[1], project_name, created_date

    def create_project_directory(
        self,
        base_path: str,
        sequence: str,
        salesman: str,
        client: str,
        project_name: str,
        created_date: str,
    ) -> str:
        """在主目录/年份/业务员下创建项目目录，并返回绝对路径。"""
        parsed_date = date.fromisoformat(created_date.strip())
        folder = f"{sequence}-{salesman}-{client}-{project_name}-{parsed_date.strftime('%Y%m%d')}"
        target_parent = os.path.abspath(os.path.join(base_path, str(parsed_date.year), salesman))
        target = os.path.join(target_parent, folder)
        if os.path.exists(target):
            raise FileExistsError(target)
        os.makedirs(target_parent, exist_ok=True)
        os.mkdir(target)
        return target

    def _project_folders(self, base_path: str) -> list[tuple[str, str, str]]:
        """列出 (年份, 业务员, 项目目录名)，保留归属信息供新增项目使用。"""
        folders: list[tuple[str, str, str]] = []
        try:
            years = os.listdir(base_path)
        except OSError:
            return folders
        for year in years:
            year_path = os.path.join(base_path, year)
            if not os.path.isdir(year_path):
                continue
            try:
                salesmen = os.listdir(year_path)
            except OSError:
                continue
            for salesman in salesmen:
                salesman_path = os.path.join(year_path, salesman)
                if not os.path.isdir(salesman_path):
                    continue
                try:
                    project_names = os.listdir(salesman_path)
                except OSError:
                    continue
                folders.extend(
                    (year, salesman, name)
                    for name in project_names
                    if os.path.isdir(os.path.join(salesman_path, name))
                )
        return folders

    def _project_folder_names(self, base_path: str) -> list[str]:
        """兼容旧调用方：只返回项目目录名。"""
        return [name for _year, _salesman, name in self._project_folders(base_path)]

    def suggest_next_sequence(self, base_path: str, salesman: str, date_text: str) -> str:
        """按"同一年、同一业务员"的已有项目，推荐下一个三位序号。"""
        try:
            target_date = date.fromisoformat(date_text.strip())
        except ValueError:
            target_date = date.today()

        target_year = str(target_date.year)
        highest = 0
        project_count = 0
        for year, owner, name in self._project_folders(base_path):
            if year != target_year or owner.casefold() != salesman.strip().casefold():
                continue
            parsed = self.parse_project_folder(name)
            if parsed is None:
                continue
            sequence, _, _, created_date = parsed
            try:
                existing = date.fromisoformat(created_date)
            except ValueError:
                continue
            if existing.year != target_date.year:
                continue
            project_count += 1
            if sequence.isdigit():
                highest = max(highest, int(sequence))
        # 正常数据按 001、002… 连续增长时等于“当年项目数 + 1”；
        # 若历史目录存在缺号，则取较大值，避免新目录与旧目录重名。
        return f"{max(highest, project_count) + 1:03d}"

    def suggest_client(self, base_path: str, salesman: str = "") -> str:
        """取最近一个项目用过的客户编号，作为默认值（大多数新项目延续同一客户）。"""
        latest: tuple[str, str] | None = None
        latest_name = ""
        for name in self._project_folder_names(base_path):
            parsed = self.parse_project_folder(name)
            if parsed is None:
                continue
            _sequence, _client, _project_name, created_date = parsed
            if latest is None or created_date > latest[0] or (
                created_date == latest[0] and name > latest_name
            ):
                latest = (created_date, parsed[1])
                latest_name = name
        return latest[1] if latest else ""

    def suggest_salesman(self, base_path: str) -> str:
        """取最近一个项目所属的业务员，作为默认值。"""
        best: tuple[str, str] | None = None
        best_name = ""
        for year in self._safe_listdir(base_path):
            year_path = os.path.join(base_path, year)
            if not os.path.isdir(year_path):
                continue
            for salesman in self._safe_listdir(year_path):
                salesman_path = os.path.join(year_path, salesman)
                if not os.path.isdir(salesman_path):
                    continue
                for name in self._safe_listdir(salesman_path):
                    parsed = self.parse_project_folder(name)
                    if parsed is None:
                        continue
                    created_date = parsed[3]
                    if best is None or created_date > best[0] or (
                        created_date == best[0] and name > best_name
                    ):
                        best = (created_date, salesman)
                        best_name = name
        return best[1] if best else ""

    @staticmethod
    def _safe_listdir(path: str) -> list[str]:
        try:
            return os.listdir(path)
        except OSError:
            return []

    def count_sample_versions(self, project_path: str) -> int:
        sample_path = os.path.join(project_path, SAMPLE_DIR_NAME)
        if not os.path.isdir(sample_path):
            return 0

        try:
            entries = list(os.scandir(sample_path))
        except OSError:
            return 0

        count = 0
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if self._is_sample_version_name(entry.name):
                count += 1
        return count

    def _is_sample_version_name(self, name: str) -> bool:
        normalized_name = name.strip()
        lowered_name = normalized_name.casefold()
        if any(marker in lowered_name for marker in SAMPLE_COPY_MARKERS):
            return False

        match = SAMPLE_VERSION_PATTERN.fullmatch(normalized_name)
        if not match:
            return False

        try:
            date(
                int(match.group("date")[0:4]),
                int(match.group("date")[4:6]),
                int(match.group("date")[6:8]),
            )
        except ValueError:
            return False

        return True

    def load_projects(self, base_path: str) -> ProjectCatalog:
        projects: list[ProjectRecord] = []
        salesmen: set[str] = set()
        clients: set[str] = set()
        chips: set[str] = set()
        packages: set[str] = set()
        years: set[str] = set()
        summary = ProjectLoadSummary()

        # 顶层到项目层都做排序，这样表格和统计结果在不同机器上更稳定、更容易对比。
        for year_dir in sorted(os.listdir(base_path)):
            year_path = os.path.join(base_path, year_dir)
            if not os.path.isdir(year_path) or not _is_ascii_year(year_dir):
                continue
            years.add(year_dir)

            try:
                salesman_dirs = sorted(os.listdir(year_path))
            except OSError:
                summary.unreadable_directories += 1
                continue

            for salesman in salesman_dirs:
                salesman_path = os.path.join(year_path, salesman)
                if not os.path.isdir(salesman_path):
                    continue

                try:
                    project_folders = sorted(os.listdir(salesman_path))
                except OSError:
                    summary.unreadable_directories += 1
                    continue

                for project_folder in project_folders:
                    full_path = os.path.join(salesman_path, project_folder)
                    if not os.path.isdir(full_path):
                        continue

                    parsed_folder = self.parse_project_folder(project_folder)
                    if parsed_folder is None:
                        summary.invalid_project_folders += 1
                        continue

                    sequence, client, project_name, created_date = parsed_folder
                    # 芯片型号与脚位只认根目录的标记文件名；标记文件没写封装就如实留空，
                    # 不去「送样」目录里找（那里是已送出的样品版本，不读、不改、不猜）。
                    chip_name, package_name = self.get_chip_info(full_path)
                    if chip_name == UNSET_OPTION:
                        summary.unresolved_chip_name += 1
                    if package_name == UNSET_OPTION:
                        summary.unresolved_package += 1
                    sample_count = self.count_sample_versions(full_path)

                    record = ProjectRecord(
                        year=year_dir,
                        sequence=sequence,
                        salesman=salesman,
                        client=client,
                        full_project_name=project_folder,
                        project_name=project_name,
                        chip_name=chip_name,
                        package_name=package_name,
                        created_date=created_date,
                        sample_count=sample_count,
                        path=full_path,
                    )
                    projects.append(record)

                    salesmen.add(salesman)
                    clients.add(client)
                    chips.add(chip_name)
                    packages.add(package_name)

        projects.sort(key=lambda item: (item.year, item.created_date), reverse=True)
        return ProjectCatalog(
            projects=projects,
            years=sorted(years, reverse=True),
            salesmen=sorted(salesmen),
            clients=sorted(clients),
            chips=sorted(chips),
            packages=sorted(packages),
            load_summary=summary,
        )

    def filter_projects(
        self,
        projects: list[ProjectRecord],
        year: str,
        salesman: str,
        client: str,
        chip: str,
        package: str,
        search_fields: list[str],
        search_keyword: str,
    ) -> list[ProjectRecord]:
        search_attrs = [
            SEARCH_FIELD_MAP[field]
            for field in search_fields
            if field in SEARCH_FIELD_MAP
        ] or [SEARCH_FIELD_MAP[field] for field in DEFAULT_SEARCH_FIELDS]
        keyword = search_keyword.strip().lower()

        filtered = [
            project for project in projects
            if (year == ALL_OPTION or project.year == year)
            and (salesman == ALL_OPTION or project.salesman == salesman)
            and (client == ALL_OPTION or project.client == client)
            and (chip == ALL_OPTION or project.chip_name == chip)
            and (package == ALL_OPTION or project.package_name == package)
            and (
                not keyword
                or any(keyword in str(getattr(project, attr)).lower() for attr in search_attrs)
            )
        ]
        filtered.sort(key=lambda item: (item.year, item.created_date), reverse=True)
        return filtered

    def build_statistics(self, projects: list[ProjectRecord], stat_type: str) -> dict[str, int]:
        stat_attr = STAT_FIELD_MAP.get(stat_type)
        if stat_attr is None:
            return {}
        counter = Counter(getattr(project, stat_attr) for project in projects)
        return dict(counter)
