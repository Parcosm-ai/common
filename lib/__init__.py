"""Shared configuration and database utilities for cursor projects."""

from lib.casted_dict import CastedDict
from lib.db_connection import DatabaseCredentials

__all__ = [
    "CastedDict",
    "DatabaseCredentials",
]
