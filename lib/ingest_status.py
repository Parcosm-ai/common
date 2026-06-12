"""Shared ingest and analyzer job status tables and accessors."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping

from psycopg2.extras import Json

from lib.db_connection import DatabaseCredentials

PCOM_PREFIX = "pcom_"
DEFAULT_STATUS_ALL_TABLE = "pcom_status_all"
DEFAULT_STATUS_LATEST_TABLE = "pcom_status_latest"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

STATUSES = frozenset(
    {
        STATUS_PENDING,
        STATUS_RUNNING,
        STATUS_COMPLETE,
        STATUS_FAILED,
        STATUS_SKIPPED,
    }
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_JOB_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SESSION_DATE_FMT = "%Y-%m-%d"


def sql_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


def pcom_table_identifier(name: str) -> str:
    validated = sql_identifier(name)
    if not validated.startswith(PCOM_PREFIX):
        raise ValueError(
            f"table {name!r} must start with prefix {PCOM_PREFIX!r}"
        )
    return validated


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_session_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(value, _SESSION_DATE_FMT).date()


def _validate_job_field(field_name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be non-empty")
    if len(cleaned) > 128:
        raise ValueError(f"{field_name} must be at most 128 characters")
    if not _JOB_KEY_RE.match(cleaned):
        raise ValueError(f"invalid {field_name}: {value!r}")
    return cleaned


def _validate_status(status: str) -> str:
    cleaned = status.strip().lower()
    if cleaned not in STATUSES:
        allowed = ", ".join(sorted(STATUSES))
        raise ValueError(f"invalid status {status!r}; expected one of: {allowed}")
    return cleaned


@dataclass(frozen=True)
class LatestStatus:
    project: str
    job_key: str
    status: str
    last_event_at: datetime
    last_success_at: datetime | None
    session_date: date | None
    artifact_version: str | None
    message: str | None
    metadata: dict[str, Any] | None
    updated_timestamp: datetime


@dataclass(frozen=True)
class LatestCompletion:
    project: str
    job_key: str
    last_success_at: datetime
    session_date: date | None
    artifact_version: str | None
    message: str | None
    metadata: dict[str, Any] | None
    updated_timestamp: datetime


class IngestStatusStore:
    """Publish and read shared ingest/analyzer status in PostgreSQL."""

    def __init__(
        self,
        db: DatabaseCredentials,
        *,
        status_all_table: str = DEFAULT_STATUS_ALL_TABLE,
        status_latest_table: str = DEFAULT_STATUS_LATEST_TABLE,
    ) -> None:
        self.db = db
        self.status_all_table = pcom_table_identifier(status_all_table)
        self.status_latest_table = pcom_table_identifier(status_latest_table)

    @classmethod
    def from_credentials(cls, db: DatabaseCredentials) -> IngestStatusStore:
        conf = db.conf
        return cls(
            db,
            status_all_table=conf.get("status_all_table", DEFAULT_STATUS_ALL_TABLE),
            status_latest_table=conf.get(
                "status_latest_table", DEFAULT_STATUS_LATEST_TABLE
            ),
        )

    def ensure_tables(self) -> None:
        all_table = self.status_all_table
        latest_table = self.status_latest_table
        ddl = f"""
            CREATE TABLE IF NOT EXISTS {all_table} (
                id BIGSERIAL PRIMARY KEY,
                project TEXT NOT NULL,
                job_key TEXT NOT NULL,
                status TEXT NOT NULL,
                event_at TIMESTAMPTZ NOT NULL,
                session_date DATE,
                artifact_version TEXT,
                message TEXT,
                metadata JSONB,
                updated_timestamp TIMESTAMPTZ NOT NULL
            );

            CREATE INDEX IF NOT EXISTS {all_table}_project_job_event_idx
                ON {all_table} (project, job_key, event_at DESC);

            CREATE TABLE IF NOT EXISTS {latest_table} (
                project TEXT NOT NULL,
                job_key TEXT NOT NULL,
                status TEXT NOT NULL,
                last_event_at TIMESTAMPTZ NOT NULL,
                last_success_at TIMESTAMPTZ,
                session_date DATE,
                artifact_version TEXT,
                message TEXT,
                metadata JSONB,
                updated_timestamp TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (project, job_key)
            );
        """
        cursor = self.db.cursor()
        try:
            cursor.execute(ddl)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            cursor.close()

    def publish_status(
        self,
        project: str,
        job_key: str,
        status: str,
        *,
        message: str | None = None,
        session_date: str | date | None = None,
        artifact_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        event_at: datetime | None = None,
    ) -> None:
        project = _validate_job_field("project", project)
        job_key = _validate_job_field("job_key", job_key)
        status = _validate_status(status)
        parsed_session_date = _parse_session_date(session_date)
        when = event_at or _utc_now()
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        metadata_value = Json(dict(metadata)) if metadata is not None else None
        last_success_at = when if status == STATUS_COMPLETE else None

        all_table = self.status_all_table
        latest_table = self.status_latest_table
        insert_all_sql = f"""
            INSERT INTO {all_table} (
                project, job_key, status, event_at, session_date,
                artifact_version, message, metadata, updated_timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        upsert_latest_sql = f"""
            INSERT INTO {latest_table} (
                project, job_key, status, last_event_at, last_success_at,
                session_date, artifact_version, message, metadata, updated_timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (project, job_key) DO UPDATE SET
                status = EXCLUDED.status,
                last_event_at = EXCLUDED.last_event_at,
                last_success_at = CASE
                    WHEN EXCLUDED.status = '{STATUS_COMPLETE}'
                    THEN EXCLUDED.last_success_at
                    ELSE {latest_table}.last_success_at
                END,
                session_date = CASE
                    WHEN EXCLUDED.status = '{STATUS_COMPLETE}'
                    THEN EXCLUDED.session_date
                    ELSE {latest_table}.session_date
                END,
                artifact_version = CASE
                    WHEN EXCLUDED.status = '{STATUS_COMPLETE}'
                    THEN EXCLUDED.artifact_version
                    ELSE {latest_table}.artifact_version
                END,
                message = EXCLUDED.message,
                metadata = EXCLUDED.metadata,
                updated_timestamp = EXCLUDED.updated_timestamp
        """
        cursor = self.db.cursor()
        try:
            cursor.execute(
                insert_all_sql,
                (
                    project,
                    job_key,
                    status,
                    when,
                    parsed_session_date,
                    artifact_version,
                    message,
                    metadata_value,
                    when,
                ),
            )
            cursor.execute(
                upsert_latest_sql,
                (
                    project,
                    job_key,
                    status,
                    when,
                    last_success_at,
                    parsed_session_date,
                    artifact_version,
                    message,
                    metadata_value,
                    when,
                ),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            cursor.close()

    def get_latest_status(
        self, project: str, job_key: str
    ) -> LatestStatus | None:
        project = _validate_job_field("project", project)
        job_key = _validate_job_field("job_key", job_key)
        latest_table = self.status_latest_table
        sql = f"""
            SELECT project, job_key, status, last_event_at, last_success_at,
                   session_date, artifact_version, message, metadata,
                   updated_timestamp
            FROM {latest_table}
            WHERE project = %s AND job_key = %s
        """
        cursor = self.db.cursor()
        try:
            cursor.execute(sql, (project, job_key))
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            return None
        return LatestStatus(
            project=row[0],
            job_key=row[1],
            status=row[2],
            last_event_at=row[3],
            last_success_at=row[4],
            session_date=row[5],
            artifact_version=row[6],
            message=row[7],
            metadata=row[8],
            updated_timestamp=row[9],
        )

    def get_latest_completion(
        self, project: str, job_key: str
    ) -> LatestCompletion | None:
        latest = self.get_latest_status(project, job_key)
        if latest is None or latest.last_success_at is None:
            return None
        return LatestCompletion(
            project=latest.project,
            job_key=latest.job_key,
            last_success_at=latest.last_success_at,
            session_date=latest.session_date,
            artifact_version=latest.artifact_version,
            message=latest.message,
            metadata=latest.metadata,
            updated_timestamp=latest.updated_timestamp,
        )

    def list_latest_statuses(self) -> list[LatestStatus]:
        latest_table = self.status_latest_table
        sql = f"""
            SELECT project, job_key, status, last_event_at, last_success_at,
                   session_date, artifact_version, message, metadata,
                   updated_timestamp
            FROM {latest_table}
            ORDER BY project, job_key
        """
        cursor = self.db.cursor()
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return [
            LatestStatus(
                project=row[0],
                job_key=row[1],
                status=row[2],
                last_event_at=row[3],
                last_success_at=row[4],
                session_date=row[5],
                artifact_version=row[6],
                message=row[7],
                metadata=row[8],
                updated_timestamp=row[9],
            )
            for row in rows
        ]
