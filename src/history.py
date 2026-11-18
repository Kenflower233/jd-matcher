"""本地分析历史：仅保存摘要与指纹，不保存JD或简历原文。"""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class HistoryRecord:
    id: int
    created_at: str
    job_title: str
    score: int
    matched_count: int
    total_requirements: int
    skill_coverage: int | None
    missing: list[str]
    requirement_statuses: dict[str, str]
    jd_fingerprint: str
    resume_fingerprint: str


@dataclass(frozen=True)
class HistoryComparison:
    score_delta: int
    resolved_gaps: list[str]
    new_gaps: list[str]
    improved_requirements: list[str]


class HistoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                job_title TEXT NOT NULL,
                score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
                matched_count INTEGER NOT NULL,
                total_requirements INTEGER NOT NULL,
                skill_coverage INTEGER,
                missing_json TEXT NOT NULL,
                requirements_json TEXT NOT NULL,
                jd_fingerprint TEXT NOT NULL,
                resume_fingerprint TEXT NOT NULL
            )
            """
        )
        return connection

    def add(
        self,
        *,
        job_title: str,
        score: int,
        matched_count: int,
        total_requirements: int,
        skill_coverage: int | None,
        missing: list[str],
        requirement_statuses: dict[str, str],
        jd_fingerprint: str,
        resume_fingerprint: str,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO analysis_history (
                    created_at, job_title, score, matched_count,
                    total_requirements, skill_coverage, missing_json,
                    requirements_json, jd_fingerprint, resume_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                    job_title.strip()[:80] or "未命名岗位",
                    score,
                    matched_count,
                    total_requirements,
                    skill_coverage,
                    json.dumps(missing, ensure_ascii=False),
                    json.dumps(requirement_statuses, ensure_ascii=False),
                    jd_fingerprint,
                    resume_fingerprint,
                ),
            )
            return int(cursor.lastrowid)

    def list(self, limit: int = 50) -> list[HistoryRecord]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def delete(self, record_id: int) -> bool:
        if not self.path.exists():
            return False
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM analysis_history WHERE id = ?", (record_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _to_record(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            id=row["id"],
            created_at=row["created_at"],
            job_title=row["job_title"],
            score=row["score"],
            matched_count=row["matched_count"],
            total_requirements=row["total_requirements"],
            skill_coverage=row["skill_coverage"],
            missing=json.loads(row["missing_json"]),
            requirement_statuses=json.loads(row["requirements_json"]),
            jd_fingerprint=row["jd_fingerprint"],
            resume_fingerprint=row["resume_fingerprint"],
        )


def compare_history(older: HistoryRecord, newer: HistoryRecord) -> HistoryComparison:
    old_missing = set(older.missing)
    new_missing = set(newer.missing)
    status_value = {"missing": 0, "partial": 1, "matched": 2}
    improved = [
        requirement
        for requirement, new_status in newer.requirement_statuses.items()
        if requirement in older.requirement_statuses
        and status_value.get(new_status, 0)
        > status_value.get(older.requirement_statuses[requirement], 0)
    ]
    return HistoryComparison(
        score_delta=newer.score - older.score,
        resolved_gaps=sorted(old_missing - new_missing),
        new_gaps=sorted(new_missing - old_missing),
        improved_requirements=sorted(improved),
    )
