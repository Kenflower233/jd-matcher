"""按需生成面试准备清单，并严格校验模型输出结构。"""
from dataclasses import dataclass

from .analyzer import AnalysisError, _parse_json
from .llm_client import LLMClient, LLMError
from .prompts import INTERVIEW_SYSTEM, build_interview_prompt


ALLOWED_CATEGORIES = {"项目追问", "技能基础", "行为经历", "岗位动机", "差距核实"}


@dataclass(frozen=True)
class InterviewQuestion:
    category: str
    question: str
    why: str
    answer_framework: str
    caution: str


@dataclass(frozen=True)
class InterviewPrep:
    questions: list[InterviewQuestion]


def validate_interview_payload(payload: dict) -> InterviewPrep:
    if set(payload) != {"questions"}:
        raise AnalysisError("面试准备结果格式错误：只允许questions字段")
    questions = payload["questions"]
    if not isinstance(questions, list) or not 4 <= len(questions) <= 8:
        raise AnalysisError("面试准备结果应包含4到8个问题")
    expected = {"category", "question", "why", "answer_framework", "caution"}
    validated: list[InterviewQuestion] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict) or set(item) != expected:
            raise AnalysisError(f"第{index}个面试问题字段不完整")
        if not all(isinstance(item[key], str) and item[key].strip() for key in expected):
            raise AnalysisError(f"第{index}个面试问题包含空内容")
        if item["category"] not in ALLOWED_CATEGORIES:
            raise AnalysisError(f"第{index}个面试问题类型不支持")
        validated.append(
            InterviewQuestion(**{key: item[key].strip() for key in expected})
        )
    return InterviewPrep(validated)


def generate_interview_prep(
    jd_text: str,
    resume_text: str,
    gaps: list[str],
    client: LLMClient,
) -> InterviewPrep:
    if not jd_text.strip() or not resume_text.strip():
        raise AnalysisError("生成面试准备前需要JD和简历内容")
    try:
        raw = client.chat(
            INTERVIEW_SYSTEM,
            build_interview_prompt(jd_text, resume_text, gaps),
        )
    except LLMError as error:
        raise AnalysisError(str(error)) from error
    return validate_interview_payload(_parse_json(raw))
