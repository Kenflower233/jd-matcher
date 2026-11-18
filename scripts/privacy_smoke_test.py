"""用合成联系方式验证真实API脱敏、占位符保留与本地恢复。"""
import json

from src.config import load_config
from src.llm_client import LLMClient
from src.privacy import redact_personal_info
from src.rewriter import rewrite_resume


ORIGINAL = """邮箱：student@example.com
电话：13812345678
项目经历：2025年使用Python分析公开数据并制作报告。
"""


def main() -> None:
    redaction = redact_personal_info(ORIGINAL)
    result = rewrite_resume(
        redaction.text,
        ["缺少SQL项目证据"],
        LLMClient(load_config()),
        scope="项目经历",
        intensity="保守",
        original_resume_text=ORIGINAL,
        privacy_replacements=redaction.replacements,
    )
    summary = {
        "redacted_items": redaction.counts,
        "email_restored": "student@example.com" in result.rewritten,
        "phone_restored": "13812345678" in result.rewritten,
        "warnings": result.warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["email_restored"] or not summary["phone_restored"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
