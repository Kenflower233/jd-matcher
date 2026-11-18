"""简历隐私信息的本地脱敏与恢复。"""
import re
from dataclasses import dataclass, field


PRIVACY_PATTERNS = (
    (
        "详细地址",
        re.compile(
            r"(?P<label>(?:(?<!项目)(?<!公司)地址|住址|现居地)\s*[:：]?\s*)"
            r"(?P<value>[^\n]{4,80})"
        ),
    ),
    ("身份证号", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)|(?<!\d)\d{15}(?!\d)")),
    ("邮箱", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("手机号", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
)


@dataclass
class PrivacyRedaction:
    text: str
    replacements: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def restore(self, text: str) -> str:
        restored = text
        for placeholder, original in self.replacements.items():
            restored = restored.replace(placeholder, original)
        return restored

    def missing_placeholders(self, text: str) -> list[str]:
        return [placeholder for placeholder in self.replacements if placeholder not in text]


def redact_personal_info(text: str) -> PrivacyRedaction:
    """仅在本地将明确的联系方式、证件号与带标签地址替换为占位符。"""
    redacted = text
    replacements: dict[str, str] = {}
    counts: dict[str, int] = {}

    for label, pattern in PRIVACY_PATTERNS:
        count = 0

        def replace(match: re.Match) -> str:
            nonlocal count
            count += 1
            placeholder = f"[[PRIVATE_{label}_{count}]]"
            if label == "详细地址":
                original = match.group("value")
                replacements[placeholder] = original
                return match.group("label") + placeholder
            replacements[placeholder] = match.group(0)
            return placeholder

        redacted = pattern.sub(replace, redacted)
        if count:
            counts[label] = count

    return PrivacyRedaction(text=redacted, replacements=replacements, counts=counts)
