"""简历分模块编辑与DOCX导出。"""
from dataclasses import dataclass
from io import BytesIO
import re

from docx import Document
from docx.shared import Pt


@dataclass(frozen=True)
class ResumeSection:
    title: str
    content: str


SECTION_TITLES = {
    "个人信息", "基本信息", "求职意向", "个人总结", "自我评价",
    "教育经历", "教育背景", "实习经历", "工作经历", "项目经历",
    "校园经历", "技能", "专业技能", "技能证书", "证书", "获奖经历",
    "personal information", "summary", "education", "experience",
    "work experience", "project experience", "projects", "skills", "awards",
}


def _normalized_heading(line: str) -> str:
    cleaned = re.sub(r"^[一二三四五六七八九十\d]+[.、．]\s*", "", line.strip())
    return cleaned.rstrip("：:").strip().lower()


def parse_resume_sections(text: str) -> list[ResumeSection]:
    """按常见中英文标题切分；无法识别时保留为一个完整模块。"""
    if not text.strip():
        return []
    sections: list[ResumeSection] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if content or current_title:
            sections.append(
                ResumeSection(current_title or "基本信息", content)
            )
        current_lines = []

    for line in text.splitlines():
        normalized = _normalized_heading(line)
        if normalized in SECTION_TITLES and len(line.strip()) <= 32:
            flush()
            current_title = line.strip().rstrip("：:")
        else:
            current_lines.append(line)
    flush()
    if len(sections) == 1 and sections[0].title == "基本信息":
        return [ResumeSection("完整简历", sections[0].content)]
    return sections


def sections_to_text(sections: list[ResumeSection]) -> str:
    blocks: list[str] = []
    for section in sections:
        title = section.title.strip()
        content = section.content.strip()
        if title == "完整简历":
            block = content
        else:
            block = "\n".join(part for part in (title, content) if part)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def build_resume_docx(sections: list[ResumeSection]) -> bytes:
    """将当前编辑稿导出为结构清晰、可继续修改的Word文档。"""
    document = Document()
    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10.5)
    for section in sections:
        if section.title != "完整简历":
            document.add_heading(section.title, level=1)
        for line in section.content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "• ", "· ")):
                document.add_paragraph(stripped[2:].strip(), style="List Bullet")
            else:
                document.add_paragraph(stripped)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
