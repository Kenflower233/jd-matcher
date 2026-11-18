"""读取课程展示使用的跨行业已验证评测基线。"""
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class EvaluationSummary:
    rows: list[dict]
    industries: int
    schema_success_rate: int
    matched_average: float
    unmatched_average: float
    separation: float


def load_evaluation_summary(dataset_path: str | Path, results_path: str | Path) -> EvaluationSummary:
    dataset_rows = [
        json.loads(line)
        for line in Path(dataset_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    scores = results.get("scores", {})
    rows: list[dict] = []
    for case in dataset_rows:
        if case["id"] not in scores:
            raise ValueError(f"评测结果缺少样例：{case['id']}")
        rows.append(
            {
                "样例": case["id"],
                "行业": case["industry"],
                "分组": "明显匹配" if case["group"] == "matched" else "明显不匹配",
                "得分": int(scores[case["id"]]),
            }
        )
    matched = [row["得分"] for row in rows if row["分组"] == "明显匹配"]
    unmatched = [row["得分"] for row in rows if row["分组"] == "明显不匹配"]
    matched_average = mean(matched)
    unmatched_average = mean(unmatched)
    return EvaluationSummary(
        rows=rows,
        industries=len({row["行业"] for row in rows}),
        schema_success_rate=int(results["schema_success_rate"] * 100 + 0.5),
        matched_average=round(matched_average, 2),
        unmatched_average=round(unmatched_average, 2),
        separation=round(matched_average - unmatched_average, 2),
    )
