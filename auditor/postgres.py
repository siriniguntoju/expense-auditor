"""Small DB-API compatibility layer; production mode uses PostgreSQL."""

import psycopg
from psycopg.rows import dict_row


class Connection:
    def __init__(self, url):
        self.conn = psycopg.connect(url, row_factory=dict_row)

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, *args):
        return self.conn.__exit__(*args)

    def execute(self, sql, args=()):
        if sql == "BEGIN IMMEDIATE":
            sql = "BEGIN"
        # Application SQL only; values remain bound parameters.
        return self.conn.execute(sql.replace("?", "%s"), args)

    def executescript(self, sql):
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        for statement in sql.split(";"):
            if statement.strip():
                self.conn.execute(statement)
