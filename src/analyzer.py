"""分析器：编排完整业务流程（输入校验 → LLM调用 → 解析 → 输出校验）。"""
import json
from dataclasses import dataclass, field

from .llm_client import LLMClient, LLMError
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .validator import check_requirement_evidence, validate_schema


class AnalysisError(Exception):
    """分析流程失败的统一异常。"""


@dataclass
class AnalysisOutput:
    """最终交付给界面层的结果。"""
    score: int
    matched: list[str]
    missing: list[str]
    suggestions: list[str]
    requirements: list[dict] = field(default_factory=list)
    score_breakdown: dict[str, int | None] = field(default_factory=dict)
    score_reasons: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


SCORE_WEIGHTS = {"skills": 50, "experience": 30, "education": 20}
REQUIREMENT_CATEGORY_WEIGHTS = {
    "skill": 50,
    "experience": 30,
    "education": 20,
    "other": 10,
}
REQUIREMENT_IMPORTANCE_WEIGHTS = {"required": 3, "preferred": 2, "bonus": 1}
REQUIREMENT_STATUS_VALUES = {"matched": 1.0, "partial": 0.5, "missing": 0.0}


def compute_score(dimensions: dict) -> int:
    """按固定权重计算总分；不适用的维度不进入分母。"""
    active = {
        name: value
        for name, value in dimensions.items()
        if value["applicable"]
    }
    if not active:
        raise AnalysisError("模型未给出任何可用的评分维度")
    total_weight = sum(SCORE_WEIGHTS[name] for name in active)
    weighted = sum(active[name]["score"] * SCORE_WEIGHTS[name] for name in active)
    return int(weighted / total_weight + 0.5)


def compute_requirement_score(requirements: list[dict]) -> int:
    """根据用户修正后的逐条要求重新计算可解释分数。"""
    if not requirements:
        raise AnalysisError("岗位要求不能为空")

    category_scores: dict[str, float] = {}
    for category in REQUIREMENT_CATEGORY_WEIGHTS:
        items = [item for item in requirements if item["category"] == category]
        if not items:
            continue
        total = sum(REQUIREMENT_IMPORTANCE_WEIGHTS[item["importance"]] for item in items)
        achieved = sum(
            REQUIREMENT_IMPORTANCE_WEIGHTS[item["importance"]]
            * REQUIREMENT_STATUS_VALUES[item["status"]]
            for item in items
        )
        category_scores[category] = achieved / total

    total_weight = sum(REQUIREMENT_CATEGORY_WEIGHTS[name] for name in category_scores)
    weighted = sum(
        category_scores[name] * REQUIREMENT_CATEGORY_WEIGHTS[name]
        for name in category_scores
    )
    return int(weighted / total_weight * 100 + 0.5)


def _parse_json(text: str) -> dict:
    """提取LLM返回内容中的第一个完整JSON对象。

    模型偶尔会在合法JSON前后附加说明、代码围栏或第二段内容。使用
    JSONDecoder.raw_decode避免这些尾随内容触发``Extra data``，同时仍由
    后续严格Schema校验保证对象结构正确。
    """
    cleaned = text.strip()
    decoder = json.JSONDecoder()
    last_error: json.JSONDecodeError | None = None

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            result, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError as error:
            last_error = error
            continue
        if isinstance(result, dict):
            return result

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as error:
        detail = last_error or error
        raise AnalysisError(f"模型返回的内容不是合法JSON：{detail}") from detail
    if not isinstance(result, dict):
        raise AnalysisError("模型返回的JSON不是对象结构")
    return result


def analyze(jd_text: str, resume_text: str, client: LLMClient) -> AnalysisOutput:
    """核心业务流程入口。

    流程：输入校验 → LLM调用 → JSON解析 → Schema校验 → 防幻觉检查
    任何一步失败都抛出带可读信息的异常，由界面层展示。
    """
    if not jd_text.strip():
        raise AnalysisError("JD内容不能为空")
    if not resume_text.strip():
        raise AnalysisError("简历内容不能为空")

    try:
        raw_text = client.chat(SYSTEM_PROMPT, build_user_prompt(jd_text, resume_text))
    except LLMError as e:
        raise AnalysisError(str(e)) from e

    raw_json = _parse_json(raw_text)

    report = validate_schema(raw_json)
    if not report.ok:
        raise AnalysisError("模型输出未通过格式校验：" + "；".join(report.errors))

    validated = report.data
    if validated is None:  # 仅用于类型收窄；正常路径不会发生
        raise AnalysisError("模型输出校验结果异常")
    data = validated.model_dump()
    warnings = check_requirement_evidence(data["requirements"], jd_text, resume_text)
    dimensions = data["dimensions"]
    matched = [
        f"{item['requirement']}（简历依据：{item['resume_evidence']}）"
        for item in data["requirements"]
        if item["status"] == "matched"
    ]
    missing = [
        item["requirement"]
        for item in data["requirements"]
        if item["status"] in {"partial", "missing"}
    ]
    return AnalysisOutput(
        score=compute_score(dimensions),
        matched=matched,
        missing=missing,
        suggestions=data["suggestions"],
        requirements=data["requirements"],
        score_breakdown={
            name: value["score"] if value["applicable"] else None
            for name, value in dimensions.items()
        },
        score_reasons={name: value["reason"] for name, value in dimensions.items()},
        warnings=warnings,
    )
