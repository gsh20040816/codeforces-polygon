from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel


def _to_datetime(value: int | str | datetime | None) -> datetime | None:
    """把 Polygon 返回的 unix 时间戳转换成 datetime。"""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromtimestamp(int(value))


class AccessType(str, Enum):
    """题目访问权限类型"""

    READ = "READ"
    WRITE = "WRITE"
    OWNER = "OWNER"


class FileType(str, Enum):
    """文件类型"""

    RESOURCE = "resource"
    SOURCE = "source"
    AUX = "aux"


class SourceType(str, Enum):
    """解法角色类型。

    Polygon 的 problem.saveFile 接口中 sourceType 实际表示编译器/源文件类型
    字符串，例如 cpp.gcc14-64-msys2-g++23；不要用这个枚举解析题目文件列表。
    """

    SOLUTION = "solution"
    VALIDATOR = "validator"
    CHECKER = "checker"
    INTERACTOR = "interactor"
    MAIN = "main"


class ResourceStage(str, Enum):
    """资源文件生效阶段"""

    COMPILE = "COMPILE"
    RUN = "RUN"


class ResourceAsset(str, Enum):
    """资源文件适用的资产类型"""

    VALIDATOR = "VALIDATOR"
    INTERACTOR = "INTERACTOR"
    CHECKER = "CHECKER"
    SOLUTION = "SOLUTION"


class SolutionTag(str, Enum):
    """
    解决方案标签

    Attributes:
        MA: 主要解法（Main solution）
        OK: 正确解法（Accepted）
        RJ: 会被评测系统拒绝的解法（Rejected）
        TL: 超时解法（Time Limit Exceeded）
        TO: 解法可能超时也可能通过（Time limit exceeded OR Accepted）
        WA: 错误答案解法（Wrong Answer）
        PE: 格式错误解法（Presentation Error）
        ML: 超内存解法（Memory Limit Exceeded）
        RE: 运行时错误解法（Runtime Error）
    """

    MA = "MA"
    OK = "OK"
    RJ = "RJ"
    TL = "TL"
    TO = "TO"
    WA = "WA"
    PE = "PE"
    ML = "ML"
    RE = "RE"


class ValidatorTestVerdict(str, Enum):
    """validator test 预期判定"""

    VALID = "VALID"
    INVALID = "INVALID"


class CheckerTestVerdict(str, Enum):
    """checker test 预期判定"""

    OK = "OK"
    WRONG_ANSWER = "WRONG_ANSWER"
    PRESENTATION_ERROR = "PRESENTATION_ERROR"
    CRASHED = "CRASHED"


class PointsPolicy(str, Enum):
    """测试组计分策略"""

    COMPLETE_GROUP = "COMPLETE_GROUP"
    EACH_TEST = "EACH_TEST"


class FeedbackPolicy(str, Enum):
    """测试组反馈策略"""

    NONE = "NONE"
    POINTS = "POINTS"
    ICPC = "ICPC"
    COMPLETE = "COMPLETE"


class PackageState(str, Enum):
    """包构建状态"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED = "FAILED"


class PackageType(str, Enum):
    """包类型"""

    STANDARD = "standard"
    LINUX = "linux"
    WINDOWS = "windows"


class ResourceAdvancedProperties(BaseModel):
    """资源文件的高级属性"""

    forTypes: str
    main: Optional[bool] = None
    stages: list[ResourceStage] = []
    assets: list[ResourceAsset] = []

    @classmethod
    def from_dict(cls, data: dict) -> "ResourceAdvancedProperties":
        parsed = dict(data)
        if "stages" in parsed and parsed["stages"] is not None:
            parsed["stages"] = [ResourceStage(stage) for stage in parsed["stages"]]
        if "assets" in parsed and parsed["assets"] is not None:
            parsed["assets"] = [ResourceAsset(asset) for asset in parsed["assets"]]
        return cls(**parsed)


class File(BaseModel):
    """
    表示一个资源、源代码或辅助文件

    Attributes:
        name: 文件名
        modificationTimeSeconds: 文件修改时间（Unix时间戳）
        length: 文件长度（字节）
        sourceType: Polygon 原始 sourceType 字符串（仅对源文件有效）
        resourceAdvancedProperties: 资源文件的高级属性（可选）
    """

    name: str
    modificationTimeSeconds: datetime
    length: int
    sourceType: Optional[str] = None
    resourceAdvancedProperties: Optional[ResourceAdvancedProperties] = None

    @classmethod
    def from_dict(cls, data: dict) -> "File":
        parsed = dict(data)
        parsed["modificationTimeSeconds"] = _to_datetime(parsed.get("modificationTimeSeconds"))
        if parsed.get("resourceAdvancedProperties"):
            parsed["resourceAdvancedProperties"] = ResourceAdvancedProperties.from_dict(
                parsed["resourceAdvancedProperties"]
            )
        return cls(**parsed)


class ProblemFiles(BaseModel):
    """题目的文件列表。"""

    resourceFiles: list[File]
    sourceFiles: list[File]
    auxFiles: list[File]

    @classmethod
    def from_dict(cls, data: dict) -> "ProblemFiles":
        return cls(
            resourceFiles=[File.from_dict(item) for item in data.get("resourceFiles", [])],
            sourceFiles=[File.from_dict(item) for item in data.get("sourceFiles", [])],
            auxFiles=[File.from_dict(item) for item in data.get("auxFiles", [])],
        )


class Solution(BaseModel):
    """
    表示题目的解决方案

    Attributes:
        name: 解决方案文件名
        modificationTimeSeconds: 修改时间（Unix时间戳）
        length: 文件长度（字节）
        sourceType: 源文件类型（必须是'solution'）
        tag: 解决方案标签，表示这个解法的类型和预期结果
    """

    name: str
    modificationTimeSeconds: datetime
    length: int
    sourceType: SourceType = SourceType.SOLUTION
    tag: SolutionTag

    @classmethod
    def from_dict(cls, data: dict) -> "Solution":
        parsed = dict(data)
        parsed["modificationTimeSeconds"] = _to_datetime(parsed.get("modificationTimeSeconds"))
        parsed["sourceType"] = SourceType.SOLUTION
        if parsed.get("tag") is not None:
            parsed["tag"] = SolutionTag(parsed["tag"])
        return cls(**parsed)

    def is_correct(self) -> bool:
        """判断是否为正确解法。"""
        return self.tag in (SolutionTag.MA, SolutionTag.OK)

    def is_wrong(self) -> bool:
        """判断是否为错误解法。"""
        return not (self.is_correct() or self.tag == SolutionTag.TO)

    def is_uncertain(self) -> bool:
        """判断是否为结果不确定的解法。"""
        return self.tag == SolutionTag.TO

    def get_verdict(self) -> str:
        """获取解法的预期判定结果。"""
        tag_verdicts = {
            SolutionTag.MA: "Accepted (Main)",
            SolutionTag.OK: "Accepted",
            SolutionTag.RJ: "Rejected",
            SolutionTag.TL: "Time Limit Exceeded",
            SolutionTag.TO: "Time Limit Exceeded or Accepted",
            SolutionTag.WA: "Wrong Answer",
            SolutionTag.PE: "Presentation Error",
            SolutionTag.ML: "Memory Limit Exceeded",
            SolutionTag.RE: "Runtime Error",
        }
        return tag_verdicts[self.tag]


class PolygonException(Exception):
    """Polygon API 异常基类"""

    pass


class PolygonNetworkError(PolygonException):
    """网络或传输层异常。"""

    pass


class PolygonHTTPError(PolygonException):
    """HTTP 状态码异常。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class PolygonBusinessError(PolygonException):
    """Polygon 返回 status!=OK 的业务异常。"""

    def __init__(
        self,
        message: str,
        *,
        comment: str | None = None,
        context: str | None = None,
    ):
        super().__init__(message)
        self.comment = comment
        self.context = context


class AccessDeniedException(PolygonBusinessError):
    """访问权限不足异常"""

    pass


T = TypeVar("T")


class LanguageMap(BaseModel, Generic[T]):
    """
    语言到特定类型的映射

    用于表示不同语言版本的内容，如题目描述、题解等。
    """

    items: dict[str, T]

    @classmethod
    def from_dict(cls, data: dict, item_class) -> "LanguageMap[T]":
        return cls(items={lang: item_class.from_dict(item_data) for lang, item_data in data.items()})

    def __getitem__(self, key: str) -> T:
        return self.items[key]

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        return self.items.get(key, default)

    def keys(self):
        return self.items.keys()

    def values(self):
        return self.items.values()

    def as_dict(self) -> dict[str, T]:
        return self.items


class ProblemInfo(BaseModel):
    """
    表示题目的基本信息

    Attributes:
        inputFile: 题目的输入文件名
        outputFile: 题目的输出文件名
        interactive: 是否为交互题
        timeLimit: 时间限制（毫秒）
        memoryLimit: 内存限制（MB）
    """

    inputFile: str
    outputFile: str
    interactive: bool
    timeLimit: int
    memoryLimit: int

    @classmethod
    def from_dict(cls, data: dict) -> "ProblemInfo":
        return cls(
            inputFile=data["inputFile"],
            outputFile=data["outputFile"],
            interactive=data.get("interactive", False),
            timeLimit=int(data["timeLimit"]),
            memoryLimit=int(data["memoryLimit"]),
        )


class Problem(BaseModel):
    """
    表示一个Polygon题目

    Attributes:
        id: 题目ID
        owner: 题目所有者的handle
        name: 题目名称
        deleted: 题目是否已删除
        favourite: 题目是否在用户的收藏夹中
        accessType: 用户对此题目的访问权限类型（READ/WRITE/OWNER）
        revision: 当前题目版本号
        latestPackage: 最新的可用包版本号
        modified: 题目是否被修改
        contestLetter: 题目在比赛中的编号（A, B, C...），可选
    """

    id: int
    owner: str
    name: str
    deleted: bool = False
    favourite: bool = False
    accessType: AccessType
    revision: Optional[int] = None
    latestPackage: Optional[int] = None
    modified: bool = False
    contestLetter: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Problem":
        try:
            required_fields = ["id", "name", "owner"]
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

            problem_data = {
                "id": int(data["id"]),
                "name": str(data["name"]),
                "owner": str(data["owner"]),
                "deleted": bool(data.get("deleted", False)),
                "favourite": bool(data.get("favourite", False)),
                "modified": bool(data.get("modified", False)),
            }

            access_type = data.get("accessType", AccessType.READ.value)
            problem_data["accessType"] = AccessType(access_type)

            if "revision" in data and data["revision"] is not None:
                problem_data["revision"] = int(data["revision"])
            if "latestPackage" in data and data["latestPackage"] is not None:
                problem_data["latestPackage"] = int(data["latestPackage"])
            if "contestLetter" in data and data["contestLetter"] is not None:
                problem_data["contestLetter"] = str(data["contestLetter"])

            return cls(**problem_data)
        except Exception as exc:
            raise ValueError(f"Failed to create Problem object: {exc}") from exc

    def __str__(self) -> str:
        if self.contestLetter:
            return f"Problem {self.contestLetter}: {self.name} (ID: {self.id})"
        return f"Problem: {self.name} (ID: {self.id})"


class Statement(BaseModel):
    """
    表示题目的陈述/描述

    Attributes:
        encoding: 陈述的编码格式
        name: 该语言下的题目名称
        legend: 题目描述
        input: 输入格式说明
        output: 输出格式说明
        scoring: 评分说明
        interaction: 交互协议说明（仅用于交互题）
        notes: 题目注释
        tutorial: 题解
    """

    encoding: str
    name: str
    legend: str
    input: str
    output: str
    scoring: Optional[str] = None
    interaction: Optional[str] = None
    notes: Optional[str] = None
    tutorial: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Statement":
        return cls(
            encoding=data["encoding"],
            name=data["name"],
            legend=data["legend"],
            input=data["input"],
            output=data["output"],
            scoring=data.get("scoring"),
            interaction=data.get("interaction"),
            notes=data.get("notes"),
            tutorial=data.get("tutorial"),
        )


class Test(BaseModel):
    """题目测试数据。"""

    index: int
    manual: bool
    input: Optional[str] = None
    description: Optional[str] = None
    useInStatements: bool
    scriptLine: Optional[str] = None
    group: Optional[str] = None
    points: Optional[float] = None
    inputForStatement: Optional[str] = None
    outputForStatement: Optional[str] = None
    verifyInputOutputForStatements: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Test":
        parsed = dict(data)
        parsed["index"] = int(parsed["index"])
        if parsed.get("points") is not None:
            parsed["points"] = float(parsed["points"])
        return cls(**parsed)


class TestGroup(BaseModel):
    """测试组。"""

    name: str
    pointsPolicy: PointsPolicy
    feedbackPolicy: FeedbackPolicy
    dependencies: list[str] = []

    @classmethod
    def from_dict(cls, data: dict) -> "TestGroup":
        parsed = dict(data)
        parsed["pointsPolicy"] = PointsPolicy(parsed["pointsPolicy"])
        parsed["feedbackPolicy"] = FeedbackPolicy(parsed["feedbackPolicy"])
        parsed["dependencies"] = list(parsed.get("dependencies", []))
        return cls(**parsed)


class Package(BaseModel):
    """题目打包产物。"""

    id: int
    revision: int
    creationTimeSeconds: datetime
    state: PackageState
    comment: str
    type: PackageType

    @classmethod
    def from_dict(cls, data: dict) -> "Package":
        parsed = dict(data)
        parsed["id"] = int(parsed["id"])
        parsed["revision"] = int(parsed["revision"])
        parsed["creationTimeSeconds"] = _to_datetime(parsed.get("creationTimeSeconds"))
        parsed["state"] = PackageState(parsed["state"])
        parsed["type"] = PackageType(parsed["type"])
        return cls(**parsed)


class ValidatorTest(BaseModel):
    """validator 测试。"""

    index: int
    input: str
    expectedVerdict: ValidatorTestVerdict
    testset: Optional[str] = None
    group: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ValidatorTest":
        parsed = dict(data)
        parsed["index"] = int(parsed["index"])
        parsed["expectedVerdict"] = ValidatorTestVerdict(parsed["expectedVerdict"])
        return cls(**parsed)


class CheckerTest(BaseModel):
    """checker 测试。"""

    index: int
    input: str
    output: str
    answer: str
    expectedVerdict: CheckerTestVerdict

    @classmethod
    def from_dict(cls, data: dict) -> "CheckerTest":
        parsed = dict(data)
        parsed["index"] = int(parsed["index"])
        parsed["expectedVerdict"] = CheckerTestVerdict(parsed["expectedVerdict"])
        return cls(**parsed)
