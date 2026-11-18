from pathlib import Path

import pytest

from src.evaluation import load_evaluation_summary


def test_load_verified_evaluation_summary():
    root = Path(__file__).parents[1]
    summary = load_evaluation_summary(
        root / "tests" / "eval_dataset.jsonl",
        root / "tests" / "eval_results.json",
    )
    assert len(summary.rows) == 6
    assert summary.industries == 3
    assert summary.schema_success_rate == 100
    assert summary.matched_average == 88.33
    assert summary.unmatched_average == 5
    assert summary.separation == 83.33


def test_evaluation_rejects_missing_result(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    results = tmp_path / "results.json"
    dataset.write_text('{"id":"case","industry":"x","group":"matched"}\n', encoding="utf-8")
    results.write_text('{"schema_success_rate":1,"scores":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="缺少样例"):
        load_evaluation_summary(dataset, results)
