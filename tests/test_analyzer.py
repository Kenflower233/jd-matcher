"""analyzer模块测试：mock LLM客户端，覆盖正常/异常/非法输出场景。"""
import json
from unittest.mock import MagicMock

import pytest

from src.analyzer import (
    AnalysisError,
    _parse_json,
    analyze,
    compute_requirement_score,
    compute_score,
)
from src.llm_client import LLMError

JD = "要求：熟悉Python，了解数据分析，有SQL经验"
RESUME = "3年Python开发经验，做过数据分析项目"

GOOD_LLM_RESPONSE = json.dumps({
    "dimensions": {
        "skills": {"score": 70, "applicable": True, "reason": "Python匹配，SQL缺失"},
        "experience": {"score": 80, "applicable": True, "reason": "有相关项目"},
        "education": {"score": 0, "applicable": False, "reason": "JD未要求学历"},
    },
    "requirements": [
        {
            "requirement": "熟悉Python",
            "category": "skill",
            "importance": "required",
            "status": "matched",
            "jd_evidence": "熟悉Python",
            "resume_evidence": "3年Python开发经验",
        },
        {
            "requirement": "有SQL经验",
            "category": "skill",
            "importance": "required",
            "status": "missing",
            "jd_evidence": "有SQL经验",
            "resume_evidence": None,
        },
    ],
    "suggestions": ["补充SQL", "量化成果", "突出项目"],
}, ensure_ascii=False)


def _mock_client(response: str) -> MagicMock:
    client = MagicMock()
    client.chat.return_value = response
    return client


def test_parse_plain_json():
    assert _parse_json('{"score": 80}') == {"score": 80}


def test_parse_json_in_markdown_block():
    text = '```json\n{"score": 80}\n```'
    assert _parse_json(text) == {"score": 80}


def test_parse_json_ignores_trailing_explanation():
    text = '{"score": 80}\n分析完成。'
    assert _parse_json(text) == {"score": 80}


def test_parse_json_ignores_leading_explanation():
    text = '以下是结果：\n{"score": 80}'
    assert _parse_json(text) == {"score": 80}


def test_parse_json_uses_first_complete_object():
    text = '{"score": 80}\n{"score": 60}'
    assert _parse_json(text) == {"score": 80}


def test_parse_invalid_json_raises():
    with pytest.raises(AnalysisError, match="合法JSON"):
        _parse_json("这不是JSON")


def test_analyze_success():
    result = analyze(JD, RESUME, _mock_client(GOOD_LLM_RESPONSE))
    assert result.score == 74
    assert result.score_breakdown["education"] is None
    assert len(result.requirements) == 2
    assert result.missing == ["有SQL经验"]
    assert len(result.suggestions) == 3


def test_analyze_accepts_valid_json_with_trailing_model_text():
    response = GOOD_LLM_RESPONSE + "\n分析完成，请核对结果。"
    result = analyze(JD, RESUME, _mock_client(response))
    assert result.score == 74
    assert result.missing == ["有SQL经验"]


def test_compute_score_renormalizes_inapplicable_dimensions():
    dimensions = {
        "skills": {"score": 100, "applicable": True},
        "experience": {"score": 0, "applicable": True},
        "education": {"score": 100, "applicable": False},
    }
    assert compute_score(dimensions) == 63


def test_compute_score_rejects_no_applicable_dimensions():
    dimensions = {
        name: {"score": 0, "applicable": False}
        for name in ("skills", "experience", "education")
    }
    with pytest.raises(AnalysisError, match="评分维度"):
        compute_score(dimensions)


def test_compute_requirement_score_uses_status_and_importance():
    requirements = [
        {"category": "skill", "importance": "required", "status": "matched"},
        {"category": "skill", "importance": "preferred", "status": "partial"},
        {"category": "experience", "importance": "required", "status": "missing"},
    ]
    assert compute_requirement_score(requirements) == 50


def test_compute_requirement_score_full_match_is_100():
    requirements = [
        {"category": "skill", "importance": "required", "status": "matched"},
        {"category": "other", "importance": "bonus", "status": "matched"},
    ]
    assert compute_requirement_score(requirements) == 100


def test_analyze_empty_input_rejected():
    with pytest.raises(AnalysisError, match="不能为空"):
        analyze("", RESUME, _mock_client(GOOD_LLM_RESPONSE))
    with pytest.raises(AnalysisError, match="不能为空"):
        analyze(JD, "  ", _mock_client(GOOD_LLM_RESPONSE))


def test_analyze_api_failure_propagates():
    client = MagicMock()
    client.chat.side_effect = LLMError("模型响应超时，请稍后重试")
    with pytest.raises(AnalysisError, match="超时"):
        analyze(JD, RESUME, client)


def test_analyze_invalid_llm_json_rejected():
    with pytest.raises(AnalysisError, match="合法JSON"):
        analyze(JD, RESUME, _mock_client("模型胡言乱语"))


def test_analyze_schema_violation_rejected():
    bad = json.dumps({"dimensions": {}, "requirements": [], "suggestions": []})
    with pytest.raises(AnalysisError, match="格式校验"):
        analyze(JD, RESUME, _mock_client(bad))


def test_analyze_grounding_warning_kept():
    response = json.dumps({
        "dimensions": {
            "skills": {"score": 60, "applicable": True, "reason": "部分匹配"},
            "experience": {"score": 0, "applicable": False, "reason": "未要求"},
            "education": {"score": 0, "applicable": False, "reason": "未要求"},
        },
        "requirements": [{
            "requirement": "精通CUDA",
            "category": "skill",
            "importance": "required",
            "status": "missing",
            "jd_evidence": "精通CUDA",
            "resume_evidence": None,
        }],
        "suggestions": ["a", "b", "c"],
    }, ensure_ascii=False)
    result = analyze(JD, RESUME, _mock_client(response))
    assert len(result.warnings) == 1
    assert "存疑" in result.warnings[0]
