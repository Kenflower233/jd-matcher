"""Streamlit界面测试：完整mock流程与重跑后的状态保持。"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _analysis_json() -> str:
    return json.dumps(
        {
            "dimensions": {
                "skills": {"score": 80, "applicable": True, "reason": "Python匹配"},
                "experience": {"score": 70, "applicable": True, "reason": "项目相关"},
                "education": {"score": 0, "applicable": False, "reason": "未要求"},
            },
            "requirements": [
                {
                    "requirement": "掌握Python",
                    "category": "skill",
                    "importance": "required",
                    "status": "matched",
                    "jd_evidence": "Python",
                    "resume_evidence": "Python",
                },
                {
                    "requirement": "掌握SQL",
                    "category": "skill",
                    "importance": "required",
                    "status": "missing",
                    "jd_evidence": "SQL",
                    "resume_evidence": None,
                },
            ],
            "suggestions": ["补充项目成果", "突出Python经验", "如实补充SQL经历"],
        },
        ensure_ascii=False,
    )


def test_app_keeps_results_after_rerun(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    responses = [
        _response(_analysis_json()),
        _response('{"skills": ["Python", "SQL"]}'),
        _response('{"skills": ["Python"]}'),
        _response("使用Python完成数据分析项目"),
    ]

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = responses
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.text_area(key="jd").input("要求Python和SQL")
        app.text_area(key="resume").input("使用Python完成数据分析项目")
        app.run(timeout=10)
        app.button(key="start_analysis").click().run(timeout=30)

        assert not app.exception
        assert app.metric[0].value == "76 / 100"
        assert len(app.tabs) == 6
        assert len(app.get("download_button")) == 3
        assert len(app.selectbox) == 3
        assert len(app.toggle) == 1
        ats_metric = next(metric for metric in app.metric if metric.label == "关键词覆盖率")
        assert ats_metric.value == "50%"

        app.run(timeout=10)
        assert not app.exception
        assert app.metric[0].value == "76 / 100"


def test_app_can_retry_only_failed_skill_step(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    responses = [
        _response(_analysis_json()),
        _response('{"skills": "Python"}'),
        _response("使用Python完成数据分析项目"),
        _response('{"skills": ["Python", "SQL"]}'),
        _response('{"skills": ["Python"]}'),
    ]

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = responses
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.text_area(key="jd").input("要求Python和SQL")
        app.text_area(key="resume").input("使用Python完成数据分析项目")
        app.run(timeout=10)
        app.button(key="start_analysis").click().run(timeout=30)

        assert app.metric[2].value == "—"
        app.button(key="retry_skill_gap").click().run(timeout=30)
        assert not app.exception
        assert app.metric[2].value == "1 / 2"


def test_app_can_compare_multiple_jobs_without_running_rewrite(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    responses = [_response(_analysis_json()), _response(_analysis_json())]

    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = responses
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.text_area(key="resume").input("使用Python完成数据分析项目")
        app.text_area(key="multi_jd_text").input(
            "岗位：数据分析\n要求Python和SQL\n---\n岗位：产品运营\n要求数据分析"
        )
        app.run(timeout=10)
        app.button(key="compare_jobs").click().run(timeout=30)

        assert not app.exception
        assert any("当前最匹配" in item.value for item in app.success)
        assert mock_openai.return_value.chat.completions.create.call_count == 2


def test_app_loads_multi_industry_demo_without_api_call(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with patch("src.llm_client.OpenAI") as mock_openai:
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.selectbox(key="demo_case").select("软件开发校招")
        app.run(timeout=10)
        app.button(key="load_demo").click().run(timeout=10)

        assert "后端开发工程师" in app.text_area(key="jd").value
        assert "Python和Flask" in app.text_area(key="resume").value

        app.button(key="load_multi_demo").click().run(timeout=10)
        assert "证券研究所｜经济政策与国际关系组" in app.text_area(
            key="multi_jd_text"
        ).value
        assert app.text_area(key="multi_jd_text").value.count("\n---\n") == 4
        assert "研究项目" in app.text_area(key="resume").value
        assert not app.button(key="compare_jobs").disabled
        mock_openai.assert_not_called()


def test_app_generates_interview_prep_on_demand(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    interview_payload = json.dumps(
        {
            "questions": [
                {
                    "category": category,
                    "question": f"问题{index}",
                    "why": "与岗位相关",
                    "answer_framework": "使用STAR并引用已有事实",
                    "caution": "简历未提供依据，请如实说明",
                }
                for index, category in enumerate(
                    ["项目追问", "技能基础", "行为经历", "差距核实"], start=1
                )
            ]
        },
        ensure_ascii=False,
    )
    responses = [
        _response(_analysis_json()),
        _response('{"skills": ["Python", "SQL"]}'),
        _response('{"skills": ["Python"]}'),
        _response("使用Python完成数据分析项目"),
        _response(interview_payload),
    ]
    with patch("src.llm_client.OpenAI") as mock_openai:
        mock_openai.return_value.chat.completions.create.side_effect = responses
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.text_area(key="jd").input("要求Python和SQL")
        app.text_area(key="resume").input("使用Python完成数据分析项目")
        app.run(timeout=10)
        app.button(key="start_analysis").click().run(timeout=30)
        assert mock_openai.return_value.chat.completions.create.call_count == 4

        app.button(key="generate_interview").click().run(timeout=30)
        assert not app.exception
        assert mock_openai.return_value.chat.completions.create.call_count == 5
        assert any("问题1" in expander.label for expander in app.expander)


def test_app_course_panel_uses_saved_synthetic_baseline(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with patch("src.llm_client.OpenAI") as mock_openai:
        app_path = Path(__file__).parents[1] / "app.py"
        app = AppTest.from_file(app_path).run(timeout=10)
        app.button(key="toggle_course_panel").click().run(timeout=10)

        assert not app.exception
        schema_metric = next(
            metric for metric in app.metric if metric.label == "Schema合格率"
        )
        assert schema_metric.value == "100%"
        mock_openai.assert_not_called()


def test_app_opens_history_panel_near_top(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path).run(timeout=10)
    app.button(key="toggle_history").click().run(timeout=10)

    assert not app.exception
    assert app.button(key="toggle_history").label == "关闭本地历史"
    assert any("本地历史 · 版本比较" in item.value for item in app.markdown)
    assert any("不保存JD、简历" in item.value for item in app.info)


def test_public_app_requires_consent_and_hides_shared_history(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setenv("PUBLIC_SESSION_ACTION_LIMIT", "3")
    monkeypatch.setenv("PUBLIC_DAILY_LLM_CALL_LIMIT", "50")
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path).run(timeout=10)
    app.text_area(key="jd").input("要求Python和SQL")
    app.text_area(key="resume").input("使用Python完成数据分析项目")
    app.run(timeout=10)

    assert not app.exception
    assert not any(button.key == "toggle_history" for button in app.button)
    assert app.button(key="start_analysis").disabled
    assert any("不会保存或共享" in item.value for item in app.caption)

    app.checkbox(key="public_privacy_consent").check().run(timeout=10)
    assert not app.button(key="start_analysis").disabled
