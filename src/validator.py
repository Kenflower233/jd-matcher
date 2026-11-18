"""输出校验：JSON Schema校验 + 业务规则校验（防幻觉）。"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class DimensionResult(BaseModel):
    """LLM对单个评分维度的语义判断；总分仍由Python计算。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    score: int = Field(ge=0, le=100)
    applicable: bool
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("评分理由不能为空")
        return value


class ScoreDimensions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skills: DimensionResult
    experience: DimensionResult
    education: DimensionResult


class RequirementResult(BaseModel):
    """单条JD要求及其简历证据。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    requirement: str = Field(min_length=1)
    category: Literal["skill", "experience", "education", "other"]
    importance: Literal["required", "preferred", "bonus"]
    status: Literal["matched", "partial", "missing"]
    jd_evidence: str = Field(min_length=1)
    resume_evidence: str | None = None

    @field_validator("requirement", "jd_evidence")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("要求与证据不能为空")
        return value

    @model_validator(mode="after")
    def matched_item_requires_resume_evidence(self) -> "RequirementResult":
        if self.resume_evidence is not None:
            self.resume_evidence = self.resume_evidence.strip() or None
        if self.status in {"matched", "partial"} and not self.resume_evidence:
            raise ValueError("已匹配或部分匹配的要求必须提供简历证据")
        return self


class AnalysisResult(BaseModel):
    """LLM输出的结构定义与硬性约束。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    dimensions: ScoreDimensions
    requirements: list[RequirementResult] = Field(min_length=1)
    suggestions: list[str] = Field(min_length=3)

    @field_validator("suggestions")
    @classmethod
    def items_must_be_nonempty_strings(cls, v: list[str]) -> list[str]:
        for item in v:
            if not item.strip():
                raise ValueError("列表元素必须是非空字符串")
        return [item.strip() for item in v]

class ValidationReport:
    """校验结果：是否通过 + 问题列表。"""

    def __init__(
        self,
        ok: bool,
        errors: list[str],
        warnings: list[str],
        data: AnalysisResult | None = None,
    ) -> None:
        self.ok = ok
        self.errors = errors
        self.warnings = warnings
        self.data = data


def validate_schema(raw_json: dict) -> ValidationReport:
    """硬性校验：结构、类型、范围。不通过则整个输出不可用。"""
    try:
        data = AnalysisResult.model_validate(raw_json)
        return ValidationReport(ok=True, errors=[], warnings=[], data=data)
    except ValidationError as e:
        errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        return ValidationReport(ok=False, errors=errors, warnings=[])


def _is_grounded(item: str, jd_lower: str) -> bool:
    """判断单条missing是否在JD中有依据。

    规则（满足其一即认为有依据）：
    1. 条目中的英文/技术词（如 Spark、C++、SQL）出现在JD中
    2. 条目中文部分的任意4字滑窗出现在JD中
    """
    stopwords = {"jd", "job", "requirement", "requirements", "resume"}
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", item)
        if token.lower() not in stopwords
    }
    if tokens and not all(token in jd_lower for token in tokens):
        return False
    if tokens:
        return True

    zh = "".join(re.findall(r"[一-鿿]", item))
    for boilerplate in ("职位描述", "岗位要求", "任职要求", "要求具备", "要求熟悉", "要求掌握", "简历未提及"):
        zh = zh.replace(boilerplate, "")
    if len(zh) < 4:
        return len(zh) >= 2 and zh in jd_lower
    return any(zh[i : i + 4] in jd_lower for i in range(len(zh) - 3))


def check_grounding(raw_json: dict, jd_text: str) -> list[str]:
    """业务规则校验：missing中的条目必须在JD原文中有依据。

    返回警告列表（不拦截输出，标记"存疑"供人工核实）。
    局限：基于子串/滑窗匹配，同义表达（如"熟悉SQL" vs "掌握数据库查询"）可能误报。
    """
    warnings: list[str] = []
    jd_lower = jd_text.lower()
    for item in raw_json.get("missing", []):
        if not _is_grounded(item, jd_lower):
            warnings.append(f"存疑：'{item}' 在JD原文中未找到明确依据，请人工核实")
    return warnings


def _quote_is_grounded(quote: str, source: str) -> bool:
    """忽略空白差异后检查短引文是否来自原文。"""
    normalized_quote = re.sub(r"\s+", "", quote).lower()
    normalized_source = re.sub(r"\s+", "", source).lower()
    return bool(normalized_quote) and normalized_quote in normalized_source


def check_requirement_evidence(
    requirements: list[dict], jd_text: str, resume_text: str
) -> list[str]:
    """校验结构化要求中的JD引文与简历引文。"""
    warnings: list[str] = []
    for item in requirements:
        requirement = item["requirement"]
        if not _quote_is_grounded(item["jd_evidence"], jd_text):
            warnings.append(f"存疑：要求“{requirement}”的JD依据未在原文中找到")
        resume_evidence = item.get("resume_evidence")
        if resume_evidence and not _quote_is_grounded(resume_evidence, resume_text):
            warnings.append(f"存疑：要求“{requirement}”的简历依据未在原文中找到")
    return warnings
