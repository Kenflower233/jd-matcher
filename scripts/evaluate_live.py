"""用跨行业小型数据集评价真实LLM评分区分度与格式合格率。"""
import json
from pathlib import Path
from statistics import mean

from src.analyzer import AnalysisError, analyze
from src.config import load_config
from src.llm_client import LLMClient


DATASET = Path(__file__).parents[1] / "tests" / "eval_dataset.jsonl"


def load_dataset() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    client = LLMClient(load_config())
    results: list[dict] = []
    for case in load_dataset():
        try:
            output = analyze(case["jd"], case["resume"], client)
            results.append(
                {
                    "id": case["id"],
                    "industry": case["industry"],
                    "group": case["group"],
                    "score": output.score,
                    "warning_count": len(output.warnings),
                    "error": None,
                }
            )
        except AnalysisError as error:
            results.append(
                {
                    "id": case["id"],
                    "industry": case["industry"],
                    "group": case["group"],
                    "score": None,
                    "warning_count": None,
                    "error": str(error),
                }
            )

    successful = [result for result in results if result["score"] is not None]
    matched_scores = [result["score"] for result in successful if result["group"] == "matched"]
    unmatched_scores = [result["score"] for result in successful if result["group"] == "unmatched"]
    summary = {
        "cases": results,
        "schema_success_rate": len(successful) / len(results),
        "matched_average": round(mean(matched_scores), 2) if matched_scores else None,
        "unmatched_average": round(mean(unmatched_scores), 2) if unmatched_scores else None,
        "separation_passed": bool(
            matched_scores
            and unmatched_scores
            and mean(matched_scores) > mean(unmatched_scores)
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if len(successful) != len(results) or not summary["separation_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
