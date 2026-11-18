"""validator模块测试：覆盖正常输入、边界、非法输入。"""
from src.validator import check_grounding, check_requirement_evidence, validate_schema

VALID_OUTPUT = {
    "dimensions": {
        "skills": {"score": 75, "applicable": True, "reason": "部分技能匹配"},
        "experience": {"score": 80, "applicable": True, "reason": "经验相关"},
        "education": {"score": 0, "applicable": False, "reason": "JD未要求"},
    },
    "requirements": [{
        "requirement": "熟悉Spark",
        "category": "skill",
        "importance": "required",
        "status": "missing",
        "jd_evidence": "熟悉Spark",
        "resume_evidence": None,
    }],
    "suggestions": ["建议1", "建议2", "建议3"],
}


def test_valid_output_passes():
    report = validate_schema(VALID_OUTPUT)
    assert report.ok, f"合法输出应通过校验，实际错误：{report.errors}"


def test_score_boundary_accepted():
    for score in (0, 100):
        dimensions = {
            **VALID_OUTPUT["dimensions"],
            "skills": {**VALID_OUTPUT["dimensions"]["skills"], "score": score},
        }
        data = {**VALID_OUTPUT, "dimensions": dimensions}
        assert validate_schema(data).ok, f"边界分数 {score} 应被接受"


def test_score_out_of_range_rejected():
    for score in (-1, 101):
        dimensions = {
            **VALID_OUTPUT["dimensions"],
            "skills": {**VALID_OUTPUT["dimensions"]["skills"], "score": score},
        }
        data = {**VALID_OUTPUT, "dimensions": dimensions}
        report = validate_schema(data)
        assert not report.ok, f"越界分数 {score} 应被拒绝"


def test_missing_field_rejected():
    data = {k: v for k, v in VALID_OUTPUT.items() if k != "requirements"}
    report = validate_schema(data)
    assert not report.ok
    assert any("requirements" in e for e in report.errors)


def test_empty_list_rejected():
    data = {**VALID_OUTPUT, "requirements": []}
    assert not validate_schema(data).ok


def test_matched_requirement_needs_resume_evidence():
    item = {
        **VALID_OUTPUT["requirements"][0],
        "status": "matched",
        "resume_evidence": None,
    }
    assert not validate_schema({**VALID_OUTPUT, "requirements": [item]}).ok


def test_score_string_is_rejected_in_strict_mode():
    dimensions = {
        **VALID_OUTPUT["dimensions"],
        "skills": {**VALID_OUTPUT["dimensions"]["skills"], "score": "75"},
    }
    assert not validate_schema({**VALID_OUTPUT, "dimensions": dimensions}).ok


def test_unknown_field_is_rejected():
    assert not validate_schema({**VALID_OUTPUT, "score": 75}).ok


def test_too_few_suggestions_rejected():
    data = {**VALID_OUTPUT, "suggestions": ["只有一条"]}
    assert not validate_schema(data).ok


def test_empty_string_item_rejected():
    item = {**VALID_OUTPUT["requirements"][0], "requirement": "  "}
    data = {**VALID_OUTPUT, "requirements": [item]}
    assert not validate_schema(data).ok


def test_grounding_passes_when_keyword_in_jd():
    jd = "要求：熟悉Spark和Hive，有大数据项目经验"
    output = {"missing": ["JD要求熟悉Spark"]}
    assert check_grounding(output, jd) == []


def test_grounding_flags_hallucinated_item():
    jd = "要求：熟悉Java开发，了解Spring框架"
    output = {"missing": ["JD要求精通CUDA编程"]}
    warnings = check_grounding(output, jd)
    assert len(warnings) == 1
    assert "存疑" in warnings[0]


def test_grounding_requires_all_technical_terms():
    jd = "要求熟悉Java开发"
    output = {"missing": ["JD要求熟悉Java和CUDA"]}
    assert len(check_grounding(output, jd)) == 1


def test_requirement_evidence_accepts_exact_quotes():
    requirements = [{
        "requirement": "熟悉Python",
        "jd_evidence": "熟悉 Python",
        "resume_evidence": "Python项目",
    }]
    assert check_requirement_evidence(
        requirements, "要求熟悉 Python", "完成Python项目"
    ) == []


def test_requirement_evidence_flags_unseen_resume_quote():
    requirements = [{
        "requirement": "熟悉Python",
        "jd_evidence": "熟悉Python",
        "resume_evidence": "五年Python经验",
    }]
    warnings = check_requirement_evidence(
        requirements, "要求熟悉Python", "完成Python项目"
    )
    assert len(warnings) == 1
    assert "简历依据" in warnings[0]
