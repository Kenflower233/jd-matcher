from src.ats import analyze_ats_keywords, count_keyword


def test_count_keyword_uses_complete_english_tokens():
    assert count_keyword("SQL SQLAlchemy MySQL", "sql") == 1
    assert count_keyword("使用Python和python完成项目", "python") == 2


def test_ats_report_coverage_and_missing_keywords():
    report = analyze_ats_keywords(
        ["Python", "SQL", "Python", "数据可视化"],
        "使用Python完成数据分析和数据可视化",
    )
    assert report.total == 3
    assert report.covered_count == 2
    assert report.coverage == 67
    assert report.missing == ["sql"]
