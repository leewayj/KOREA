"""Shared schema inventory for migration creation and startup validation."""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SchemaObject:
    kind: str
    sql: str


def read_objects(db):
    return {name: SchemaObject(kind, sql) for name, kind, sql in db.execute('''
        SELECT name,type,sql FROM sqlite_master
        WHERE type IN ('table','index','view','trigger') AND sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%' ORDER BY rowid
    ''')}


def load_schema(path: Path):
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript(path.read_text(encoding='utf-8'))
        return read_objects(db)
