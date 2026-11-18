import hashlib

from src.history import HistoryStore, compare_history


def _add(store: HistoryStore, *, score: int, missing: list[str], statuses: dict[str, str]) -> int:
    return store.add(
        job_title="数据分析实习生",
        score=score,
        matched_count=sum(status == "matched" for status in statuses.values()),
        total_requirements=len(statuses),
        skill_coverage=67,
        missing=missing,
        requirement_statuses=statuses,
        jd_fingerprint=hashlib.sha256(b"jd").hexdigest(),
        resume_fingerprint=hashlib.sha256(str(score).encode()).hexdigest(),
    )


def test_history_store_saves_only_summary_and_can_delete(tmp_path):
    path = tmp_path / "history.db"
    store = HistoryStore(path)
    record_id = _add(
        store,
        score=60,
        missing=["SQL"],
        statuses={"Python": "matched", "SQL": "missing"},
    )
    records = store.list()
    assert len(records) == 1
    assert records[0].id == record_id
    assert records[0].job_title == "数据分析实习生"
    assert records[0].missing == ["SQL"]
    schema = path.read_bytes()
    assert b"resume_text" not in schema
    assert store.delete(record_id)
    assert store.list() == []


def test_compare_history_finds_score_and_gap_changes(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    _add(
        store,
        score=55,
        missing=["SQL", "Tableau"],
        statuses={"Python": "partial", "SQL": "missing", "Tableau": "missing"},
    )
    _add(
        store,
        score=75,
        missing=["Tableau", "沟通"],
        statuses={"Python": "matched", "SQL": "matched", "Tableau": "missing", "沟通": "missing"},
    )
    newer, older = store.list()
    result = compare_history(older, newer)
    assert result.score_delta == 20
    assert result.resolved_gaps == ["SQL"]
    assert result.new_gaps == ["沟通"]
    assert result.improved_requirements == ["Python", "SQL"]
