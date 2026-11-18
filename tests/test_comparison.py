import pytest

from src.analyzer import AnalysisOutput
from src.comparison import (
    comparison_row,
    parse_multi_jds,
    rank_comparison_rows,
    recommendation_for_score,
)


def test_parse_multi_jds_with_optional_titles():
    jobs = parse_multi_jds(
        "岗位：数据分析\n要求Python和SQL\n---\n负责内容运营和数据复盘"
    )
    assert jobs[0].title == "数据分析"
    assert jobs[0].text == "要求Python和SQL"
    assert jobs[1].title == "岗位 2"
    assert "内容运营" in jobs[1].text


def test_parse_multi_jds_rejects_empty_named_job_and_more_than_five():
    with pytest.raises(ValueError, match="缺少职位描述"):
        parse_multi_jds("岗位：空岗位")
    with pytest.raises(ValueError, match="最多比较 5"):
        parse_multi_jds("\n---\n".join(f"JD {index}" for index in range(6)))


def test_comparison_row_and_ranking():
    result = AnalysisOutput(
        score=72,
        matched=[],
        missing=[],
        suggestions=[],
        requirements=[
            {"requirement": "Python", "status": "matched"},
            {"requirement": "SQL", "status": "missing"},
        ],
    )
    row = comparison_row("分析岗", result)
    assert row["明确匹配"] == "1/2"
    assert row["主要差距"] == "SQL"
    assert recommendation_for_score(72) == "可以投递，先补主要短板"
    rows = rank_comparison_rows([row, {**row, "岗位": "开发岗", "匹配度": 85}])
    assert rows[0]["岗位"] == "开发岗"
