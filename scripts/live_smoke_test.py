"""使用合成数据执行一次真实API全流程；不会打印密钥或完整改写稿。"""
import json
import time

from src.analyzer import AnalysisError, analyze
from src.config import load_config
from src.llm_client import LLMClient
from src.rewriter import rewrite_resume
from src.skills import analyze_skill_gap


JD = """某金融科技团队招聘数据分析实习生：
1. 熟练使用Python和SQL进行数据清洗与分析；
2. 有数据可视化项目经验，能够使用Excel；
3. 具备良好的沟通能力，本科及以上学历。
"""

RESUME = """某大学统计学本科生，预计2027年毕业。
项目经历：使用Python和Pandas清洗公开交易数据，使用Matplotlib制作可视化报告。
技能：Python、Excel、Pandas、Matplotlib。
"""


def main() -> None:
    started = time.perf_counter()
    client = LLMClient(load_config())
    analysis = analyze(JD, RESUME, client)
    gap = analyze_skill_gap(JD, RESUME, client)
    rewrite = rewrite_resume(RESUME, analysis.missing, client)
    summary = {
        "score": analysis.score,
        "score_breakdown": analysis.score_breakdown,
        "matched_count": len(analysis.matched),
        "missing_count": len(analysis.missing),
        "suggestion_count": len(analysis.suggestions),
        "analysis_warnings": analysis.warnings,
        "matched_skills": gap.matched,
        "missing_skills": gap.missing,
        "rewrite_length": len(rewrite.rewritten),
        "rewrite_warnings": rewrite.warnings,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AnalysisError, RuntimeError) as error:
        raise SystemExit(f"真实API验证失败：{error}") from error
