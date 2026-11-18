"""ATS关键词覆盖：使用确定性字符串规则统计，不参与综合匹配分数。"""
from dataclasses import dataclass
import re

from .skills import normalize_skills


@dataclass(frozen=True)
class ATSKeyword:
    keyword: str
    occurrences: int

    @property
    def covered(self) -> bool:
        return self.occurrences > 0


@dataclass(frozen=True)
class ATSReport:
    keywords: list[ATSKeyword]

    @property
    def covered_count(self) -> int:
        return sum(item.covered for item in self.keywords)

    @property
    def total(self) -> int:
        return len(self.keywords)

    @property
    def coverage(self) -> int:
        if not self.total:
            return 0
        return int(self.covered_count / self.total * 100 + 0.5)

    @property
    def missing(self) -> list[str]:
        return [item.keyword for item in self.keywords if not item.covered]


def count_keyword(text: str, keyword: str) -> int:
    """统计完整英文词元或中文子串，避免SQL命中MySQL中的局部字符。"""
    if not keyword.strip():
        return 0
    if re.search(r"[A-Za-z0-9]", keyword):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])"
        return len(re.findall(pattern, text, flags=re.IGNORECASE))
    return text.count(keyword)


def analyze_ats_keywords(jd_keywords: list[str], resume_text: str) -> ATSReport:
    keywords = normalize_skills(jd_keywords)
    return ATSReport(
        keywords=[
            ATSKeyword(keyword=keyword, occurrences=count_keyword(resume_text, keyword))
            for keyword in keywords
        ]
    )
