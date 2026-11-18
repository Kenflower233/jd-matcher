"""rewriter模块测试：事实提取、事实保持校验、改写流程（mock）。"""
from unittest.mock import MagicMock

import pytest

from src.analyzer import AnalysisError
from src.llm_client import LLMError
from src.rewriter import check_facts_preserved, check_new_numbers, extract_facts, rewrite_resume

ORIGINAL = "2023年在ABC公司实习，用Python处理数据，效率提升30%，掌握SQL"


def test_extract_facts_finds_years_numbers_terms():
    facts = extract_facts(ORIGINAL)
    assert "2023" in facts
    assert "30%" in facts
    assert "ABC" in facts
    assert "Python" in facts


def test_facts_preserved_passes_when_all_kept():
    rewritten = "2023年于ABC公司实习，使用Python处理数据，效率提升30%，熟练掌握SQL"
    assert check_facts_preserved(ORIGINAL, rewritten) == []


def test_facts_preserved_flags_dropped_year():
    rewritten = "在某公司实习，使用Python处理数据，效率提升30%，掌握SQL"
    warnings = check_facts_preserved(ORIGINAL, rewritten)
    assert any("2023" in w for w in warnings)


def test_facts_preserved_flags_dropped_number():
    rewritten = "2023年在ABC公司实习，用Python处理数据，掌握SQL"
    warnings = check_facts_preserved(ORIGINAL, rewritten)
    assert any("30%" in w for w in warnings)


def test_fact_matching_uses_complete_number_tokens():
    warnings = check_facts_preserved("完成3个项目", "完成30个项目")
    assert any("'3'" in warning for warning in warnings)


def test_new_number_is_flagged():
    warnings = check_new_numbers("负责数据分析", "负责数据分析，效率提升20%")
    assert any("20%" in warning for warning in warnings)


def test_rewrite_success():
    client = MagicMock()
    client.chat.return_value = "2023年在ABC公司实习，用Python处理数据，效率提升30%，精通SQL"
    result = rewrite_resume(ORIGINAL, ["缺Spark"], client)
    assert result.warnings == []


def test_rewrite_empty_input_rejected():
    with pytest.raises(AnalysisError, match="不能为空"):
        rewrite_resume("  ", ["缺Spark"], MagicMock())


def test_rewrite_empty_llm_output_rejected():
    client = MagicMock()
    client.chat.return_value = "   "
    with pytest.raises(AnalysisError, match="空改写稿"):
        rewrite_resume(ORIGINAL, ["缺Spark"], client)


def test_rewrite_api_failure_propagates():
    client = MagicMock()
    client.chat.side_effect = LLMError("模型响应超时，请稍后重试")
    with pytest.raises(AnalysisError, match="超时"):
        rewrite_resume(ORIGINAL, ["缺Spark"], client)


def test_rewrite_passes_scope_and_intensity_to_prompt():
    client = MagicMock()
    client.chat.return_value = ORIGINAL
    rewrite_resume(
        ORIGINAL,
        ["缺Spark"],
        client,
        scope="项目经历",
        intensity="保守",
    )
    user_prompt = client.chat.call_args.args[1]
    assert "【改写范围】项目经历" in user_prompt
    assert "【改写强度】保守" in user_prompt


def test_rewrite_restores_privacy_placeholders():
    placeholder = "[[PRIVATE_邮箱_1]]"
    original = "邮箱：student@example.com\n使用Python完成项目"
    redacted = f"邮箱：{placeholder}\n使用Python完成项目"
    client = MagicMock()
    client.chat.return_value = redacted
    result = rewrite_resume(
        redacted,
        [],
        client,
        original_resume_text=original,
        privacy_replacements={placeholder: "student@example.com"},
    )
    assert "student@example.com" in result.rewritten
    assert result.warnings == []


def test_rewrite_warns_when_privacy_placeholder_is_dropped():
    placeholder = "[[PRIVATE_邮箱_1]]"
    client = MagicMock()
    client.chat.return_value = "使用Python完成项目"
    result = rewrite_resume(
        f"邮箱：{placeholder}\n使用Python完成项目",
        [],
        client,
        original_resume_text="邮箱：student@example.com\n使用Python完成项目",
        privacy_replacements={placeholder: "student@example.com"},
    )
    assert any("隐私占位符缺失" in warning for warning in result.warnings)
