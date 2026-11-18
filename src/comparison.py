"""多岗位比较：解析多个JD并整理可排序的比较结果。"""
from dataclasses import dataclass
import re

from .analyzer import AnalysisOutput


MAX_COMPARISON_JOBS = 5


@dataclass(frozen=True)
class JobDescription:
    title: str
    text: str


def parse_multi_jds(text: str) -> list[JobDescription]:
    """解析用单独一行 ``---`` 分隔的多个JD。

    每段首行可以写“岗位：名称”或“职位：名称”；没有标题时使用顺序名称，
    并保留全部原文作为JD内容。
    """
    blocks = re.split(r"(?m)^\s*---+\s*$", text.strip()) if text.strip() else []
    jobs: list[JobDescription] = []
    title_pattern = re.compile(r"^(?:岗位|职位|名称)\s*[：:]\s*(.+)$")
    for index, block in enumerate(blocks, start=1):
        lines = [line.rstrip() for line in block.strip().splitlines()]
        if not any(line.strip() for line in lines):
            continue
        first_index = next(i for i, line in enumerate(lines) if line.strip())
        match = title_pattern.match(lines[first_index].strip())
        if match:
            title = match.group(1).strip()
            content_lines = lines[:first_index] + lines[first_index + 1 :]
            content = "\n".join(content_lines).strip()
        else:
            title = f"岗位 {index}"
            content = "\n".join(lines).strip()
        if not content:
            raise ValueError(f"“{title}”缺少职位描述正文")
        jobs.append(JobDescription(title=title[:40], text=content))
    if len(jobs) > MAX_COMPARISON_JOBS:
        raise ValueError(f"一次最多比较 {MAX_COMPARISON_JOBS} 个岗位")
    return jobs


def recommendation_for_score(score: int) -> str:
    if score >= 80:
        return "优先投递"
    if score >= 65:
        return "可以投递，先补主要短板"
    if score >= 50:
        return "谨慎投递，建议先优化简历"
    return "当前匹配较弱"


def comparison_row(title: str, result: AnalysisOutput) -> dict:
    """将单岗位分析整理为界面可直接展示的一行。"""
    matched = sum(item["status"] == "matched" for item in result.requirements)
    gaps = [
        item["requirement"]
        for item in result.requirements
        if item["status"] in {"partial", "missing"}
    ]
    return {
        "岗位": title,
        "匹配度": result.score,
        "明确匹配": f"{matched}/{len(result.requirements)}",
        "主要差距": "；".join(gaps[:3]) or "暂无明显差距",
        "建议": recommendation_for_score(result.score),
    }


def rank_comparison_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (-int(row["匹配度"]), str(row["岗位"])))
