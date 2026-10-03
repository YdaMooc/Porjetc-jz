from dataclasses import dataclass


DISPLAY_SEQUENCE = "\u5e8f\u53f7"
DISPLAY_YEAR = "\u5e74\u4efd"
DISPLAY_SALESMAN = "\u4e1a\u52a1\u5458"
DISPLAY_CLIENT = "\u5ba2\u6237"
DISPLAY_PROJECT_NAME = "\u9879\u76ee\u540d\u79f0"
DISPLAY_CHIP_NAME = "\u82af\u7247\u578b\u53f7"
DISPLAY_PACKAGE = "\u811a\u4f4d"
DISPLAY_CREATED_DATE = "\u7acb\u9879\u65e5\u671f"
DISPLAY_SAMPLE_COUNT = "\u9001\u6837\u6b21\u6570"
DISPLAY_WORK_TODAY = "\u4eca\u65e5\u5f00\u53d1"
DISPLAY_WORK_TOTAL = "\u7d2f\u8ba1\u5f00\u53d1"


@dataclass(slots=True)
class ProjectRecord:
    year: str
    sequence: str
    salesman: str
    client: str
    full_project_name: str
    project_name: str
    chip_name: str
    package_name: str
    created_date: str
    sample_count: int
    path: str

    def to_display_dict(self, index: int) -> dict[str, str]:
        return {
            DISPLAY_SEQUENCE: str(index),
            DISPLAY_YEAR: self.year,
            DISPLAY_SALESMAN: self.salesman,
            DISPLAY_CLIENT: self.client,
            DISPLAY_PROJECT_NAME: self.project_name,
            DISPLAY_CHIP_NAME: self.chip_name,
            DISPLAY_PACKAGE: self.package_name,
            DISPLAY_CREATED_DATE: self.created_date,
            DISPLAY_SAMPLE_COUNT: str(self.sample_count),
        }
