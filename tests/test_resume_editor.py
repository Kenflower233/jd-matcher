from io import BytesIO

from docx import Document

from src.resume_editor import (
    ResumeSection,
    build_resume_docx,
    parse_resume_sections,
    sections_to_text,
)


def test_parse_and_rebuild_resume_sections():
    sections = parse_resume_sections(
        "姓名：示例\n\n教育经历\n某大学 本科\n\n项目经历：\n使用Python分析公开数据"
    )
    assert [section.title for section in sections] == ["基本信息", "教育经历", "项目经历"]
    rebuilt = sections_to_text(sections)
    assert "姓名：示例" in rebuilt
    assert "项目经历\n使用Python" in rebuilt


def test_unstructured_resume_stays_in_one_section():
    sections = parse_resume_sections("使用Python完成课程项目")
    assert sections == [ResumeSection("完整简历", "使用Python完成课程项目")]
    assert sections_to_text(sections) == "使用Python完成课程项目"


def test_build_resume_docx_contains_sections_and_content():
    payload = build_resume_docx(
        [ResumeSection("技能", "Python\n- SQL"), ResumeSection("项目经历", "公开数据项目")]
    )
    document = Document(BytesIO(payload))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "技能" in text
    assert "Python" in text
    assert "SQL" in text
    assert "公开数据项目" in text
