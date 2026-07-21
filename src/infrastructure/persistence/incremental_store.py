"""Persistent success-only quota for manual group-analysis commands."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class ManualAnalysisQuotaStore:
    """Stores only successfully delivered image reports.

    The caller checks availability before work, then records success only after
    the platform adapter confirms image delivery.  This intentionally favours a
    rare extra allowance after a process crash over charging a failed report.
    """

    def __init__(self, data_dir: str | Path, timezone_name: str = "Asia/Taipei"):
        self._db_path = Path(data_dir) / "manual_analysis_quota.sqlite3"
        self._timezone_name = timezone_name
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS successful_manual_analysis (
                    platform_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (platform_id, user_id, group_id, local_date)
                )
                """
            )
            # Forward-compatible migration for databases created by v0.1.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(successful_manual_analysis)")}
            if "success_count" not in columns:
                conn.execute("ALTER TABLE successful_manual_analysis ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0")
                conn.execute("UPDATE successful_manual_analysis SET success_count = 1")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_manual_analysis_quota_date "
                "ON successful_manual_analysis(local_date)"
            )

    def _today(self) -> str:
        try:
            tz = ZoneInfo(self._timezone_name)
        except Exception:
            tz = ZoneInfo("Asia/Taipei")
        return datetime.now(tz).date().isoformat()

    def is_limit_reached(self, platform_id: str, user_id: str, group_id: str, limit: int) -> bool:
        if limit <= 0:
            return False
        today = self._today()
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT success_count FROM successful_manual_analysis
                WHERE platform_id = ? AND user_id = ? AND group_id = ? AND local_date = ?
                """,
                (platform_id, user_id, group_id, today),
            ).fetchone()
        return bool(row and int(row[0]) >= limit)

    def mark_success(self, platform_id: str, user_id: str, group_id: str) -> None:
        today = self._today()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO successful_manual_analysis
                    (platform_id, user_id, group_id, local_date, success_count, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(platform_id, user_id, group_id, local_date)
                DO UPDATE SET success_count = success_count + 1
                """,
                (platform_id, user_id, group_id, today, datetime.utcnow().isoformat()),
            )
            # Retain only a modest history; quota only needs the current day.
            conn.execute(
                "DELETE FROM successful_manual_analysis WHERE local_date < date(?, '-14 days')",
                (today,),
            )
