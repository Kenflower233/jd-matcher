from src.comparison import parse_multi_jds
from src.demo_data import DEMO_CASES, MULTI_JD_DEMO_RESUME, MULTI_JD_DEMO_TEXT


def test_demo_cases_cover_multiple_industries_and_are_complete():
    assert len(DEMO_CASES) >= 5
    assert "证券研究实习" in DEMO_CASES
    assert "软件开发校招" in DEMO_CASES
    for case in DEMO_CASES.values():
        assert "【" in case["jd"]
        assert "任职要求" in case["jd"]
        assert "教育经历" in case["resume"]
        assert any(
            heading in case["resume"]
            for heading in ("实习经历", "实践经历", "项目经历", "校园经历")
        )


def test_multi_job_demo_has_five_related_jobs_and_structured_resume():
    jobs = parse_multi_jds(MULTI_JD_DEMO_TEXT)
    assert len(jobs) == 5
    assert all("任职要求" in job.text for job in jobs)
    assert "教育经历" in MULTI_JD_DEMO_RESUME
    assert "研究项目" in MULTI_JD_DEMO_RESUME
