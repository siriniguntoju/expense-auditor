import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        if not str(path).startswith("postgresql://"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, report_id TEXT NOT NULL, status TEXT NOT NULL, packet TEXT, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY, participant TEXT NOT NULL, report_id TEXT NOT NULL, condition TEXT NOT NULL, started TEXT NOT NULL, finished TEXT, seconds REAL, decision TEXT, mode TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS trial_assignment ON trials(participant,report_id,condition);
            """)

    def connect(self):
        if self.path.startswith("postgresql://"):
            from auditor.postgres import Connection

            return Connection(self.path)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def start(self, run_id, report_id):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, report_id, "running", None, now())
            )

    def event(self, run_id, kind, body):
        with self.connect() as db:
            db.execute(
                "INSERT INTO events(run_id,kind,body,created) VALUES(?,?,?,?)",
                (run_id, kind, json.dumps(body), now()),
            )

    def finish(self, run_id, packet):
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status='pending_review',packet=? WHERE id=?",
                (json.dumps(packet), run_id),
            )

    def fail(self, run_id):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed' WHERE id=? AND status='running'", (run_id,))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed' WHERE status='running'")

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["packet"] = json.loads(row["packet"]) if row["packet"] else None
            result["events"] = [
                dict(r, body=json.loads(r["body"]))
                for r in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,))
            ]
            return result

    def recent(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,report_id,status,created FROM runs ORDER BY created DESC LIMIT 50"
                )
            ]

    def review(self, run_id, action, comment):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            sql = "SELECT status FROM runs WHERE id=?"
            if self.path.startswith("postgresql://"):
                sql += " FOR UPDATE"
            row = db.execute(sql, (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["status"] not in {"pending_review", "approved", "rejected"}:
                raise ValueError("Only completed runs can be reviewed")
            if action != "comment":
                if row["status"] != "pending_review":
                    raise ValueError("This run already has a decision")
                db.execute(
                    "UPDATE runs SET status=? WHERE id=?",
                    ("approved" if action == "approve" else "rejected", run_id),
                )
            elif not comment.strip():
                raise ValueError("Enter a comment")
            db.execute(
                "INSERT INTO events(run_id,kind,body,created) VALUES(?,?,?,?)",
                (run_id, "review", json.dumps(dict(action=action, comment=comment)), now()),
            )
        return self.get(run_id)
