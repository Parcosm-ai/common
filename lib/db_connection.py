"""PostgreSQL connection helper using CastedDict credentials files."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from lib.casted_dict import CastedDict


class DatabaseCredentials:
    """Open a psycopg2 connection from a tab-separated credentials conf file."""

    def create_connection(self):
        conf = self.conf
        if conf.get("service", None):
            conn = psycopg2.connect(
                service=conf["service"], options=conf.get("db_opts", None)
            )
        else:
            conn = psycopg2.connect(
                database=conf.get("database", None),
                user=conf.get("user", None),
                password=conf.get("password", None),
                host=conf.get("host", None),
                port=conf.get("port", None),
                options=conf.get("db_opts", None),
            )

        schema = conf.get("schema", None)
        DatabaseCredentials.set_schema(schema, conn)
        return conn

    def engine(self):
        conn = self.create_connection()
        return create_engine(
            "postgresql+psycopg2://", creator=lambda: conn, poolclass=NullPool
        )

    @staticmethod
    def set_schema(schema, conn) -> None:
        if schema:
            first_schema = schema.split(",")[0].strip()
            conn.cursor().execute(f"create schema if not exists {first_schema}")
            conn.cursor().execute(f"set search_path to {schema}")
            conn.commit()

    def __init__(self, credentials_file: str, db_opts: str | None = None):
        """
        Args:
            credentials_file: Path to ``db_credentials.conf`` (absolute or
                resolvable via cwd / ``sys.path``). Each project should pass
                its own resolved path (e.g. from a ``*_paths`` or ``conf_paths``
                module); this package does not assume a repo layout.
        """
        self.conf = CastedDict(credentials_file)
        self.conn = self.create_connection()
        self.print_sql = False

    def cursor(self):
        return self.conn.cursor()

    def get_conn(self):
        return self.conn

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()

    def run_sql_file(self, sql_path: Path | str, cursor) -> None:
        path = Path(sql_path)
        sql_text = path.read_text(encoding="utf-8")
        try:
            cursor.execute(sql_text)
            if self.print_sql:
                print(sql_text)
                print(cursor.statusmessage)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def sql(self, sql: str, cursor=None) -> None:
        if cursor is None:
            cursor = self.cursor()
        cursor.execute(sql)
        if self.print_sql:
            print(sql)
            print(cursor.statusmessage)

    def move_schema(
        self,
        table_names: Sequence[str],
        from_schema: str,
        to_schema: str,
        recycle_bin_schema: str,
    ) -> None:
        cursor = self.cursor()
        self.sql(f"create schema if not exists {recycle_bin_schema}", cursor)
        for table_name in table_names:
            self.sql(
                f"drop table if exists {recycle_bin_schema}.{table_name} cascade;",
                cursor,
            )
            self.sql(
                f"alter table if exists {to_schema}.{table_name} set schema {recycle_bin_schema}",
                cursor,
            )
            self.sql(
                f"alter table {from_schema}.{table_name} set schema {to_schema}",
                cursor,
            )
        self.commit()
        cursor.close()
