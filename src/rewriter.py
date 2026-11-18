"""简历改写：LLM生成改写稿，Python校验事实未被篡改。

核心约束：改写只能优化表达，不得编造或改动事实（年份、数字、公司/学校名）。
"""
import re
from collections import Counter
from dataclasses import dataclass, field

from .analyzer import AnalysisError
from .llm_client import LLMClient, LLMError
from .prompts import REWRITE_SYSTEM, build_rewrite_prompt


@dataclass
class RewriteOutput:
    rewritten: str
    warnings: list[str] = field(default_factory=list)


NUMBER_PATTERN = re.compile(r"(?<!\d)\d+(?:\.\d+)?%?(?!\d)")
TERM_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9+#.\-]{1,}(?![A-Za-z0-9])")


def _extract_fact_counts(text: str) -> Counter[str]:
    """按完整词元计数，避免把3误认为30的一部分。"""
    facts = NUMBER_PATTERN.findall(text)
    facts.extend(TERM_PATTERN.findall(text))
    return Counter(fact.lower() for fact in facts)


def extract_facts(text: str) -> set[str]:
    """从文本提取可核验事实：年份、含数字的量化表述、大写缩写词。"""
    display: dict[str, str] = {}
    for fact in NUMBER_PATTERN.findall(text) + TERM_PATTERN.findall(text):
        display.setdefault(fact.lower(), fact)
    return set(display.values())


def check_facts_preserved(original: str, rewritten: str) -> list[str]:
    """校验：原简历中的事实必须出现在改写稿中，缺失则报警告。

    返回警告列表（不拦截，供人工核实）。
    局限：无法发现"数字被改成别的值"，只能发现"数字消失了"。
    """
    warnings: list[str] = []
    original_counts = _extract_fact_counts(original)
    rewritten_counts = _extract_fact_counts(rewritten)
    for fact, expected_count in sorted(original_counts.items()):
        actual_count = rewritten_counts[fact]
        if actual_count < expected_count:
            warnings.append(
                f"事实缺失：原简历中的 '{fact}' 出现 {expected_count} 次，"
                f"改写稿中仅出现 {actual_count} 次，请核实"
            )
    return warnings


def check_new_numbers(original: str, rewritten: str) -> list[str]:
    """发现改写稿中新出现的量化事实，避免模型擅自补数字。"""
    original_counts = Counter(NUMBER_PATTERN.findall(original))
    rewritten_counts = Counter(NUMBER_PATTERN.findall(rewritten))
    warnings: list[str] = []
    for fact, count in sorted(rewritten_counts.items()):
        if count > original_counts[fact]:
            warnings.append(f"疑似新增事实：改写稿新增了数字 '{fact}'，请确认并非模型编造")
    return warnings


def rewrite_resume(
    resume_text: str,
    missing: list[str],
    client: LLMClient,
    *,
    scope: str = "整份简历",
    intensity: str = "标准",
    original_resume_text: str | None = None,
    privacy_replacements: dict[str, str] | None = None,
) -> RewriteOutput:
    """完整流程：LLM改写 → 隐私恢复 → 事实保持校验。"""
    if not resume_text.strip():
        raise AnalysisError("简历内容不能为空")
    if scope not in {"整份简历", "项目经历", "个人总结", "技能部分"}:
        raise AnalysisError("不支持的改写范围")
    if intensity not in {"保守", "标准", "深度"}:
        raise AnalysisError("不支持的改写强度")
    try:
        rewritten = client.chat(
            REWRITE_SYSTEM,
            build_rewrite_prompt(resume_text, missing, scope, intensity),
            json_mode=False,
        )
    except LLMError as e:
        raise AnalysisError(str(e)) from e
    rewritten = rewritten.strip()
    if not rewritten:
        raise AnalysisError("模型返回了空改写稿，请重试")

    privacy_replacements = privacy_replacements or {}
    missing_placeholders = [
        placeholder for placeholder in privacy_replacements if placeholder not in rewritten
    ]
    for placeholder, original in privacy_replacements.items():
        rewritten = rewritten.replace(placeholder, original)

    validation_source = original_resume_text or resume_text
    warnings = (
        check_facts_preserved(validation_source, rewritten)
        + check_new_numbers(validation_source, rewritten)
    )
    warnings.extend(
        f"隐私占位符缺失：模型未保留 {placeholder}，对应原文可能未出现在改写稿中"
        for placeholder in missing_placeholders
    )
    return RewriteOutput(
        rewritten=rewritten,
        warnings=list(dict.fromkeys(warnings)),
    )
