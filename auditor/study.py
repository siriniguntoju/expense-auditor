"""Human-only timing study. Never synthesizes participant measurements."""

import json
from datetime import datetime
from statistics import median
from uuid import uuid4

from auditor.paths import ROOT
from auditor.store import now

CASES = ["report-01", "report-03", "report-06", "report-07"]


def start(store, participant, report_id, condition, mode):
    if report_id not in CASES or condition not in {"manual", "assisted"}:
        raise ValueError("Unknown study assignment")
    if mode not in {"fixture_replay", "gemini_cached"}:
        raise ValueError("Studies use fixture or cached extraction to avoid live quota latency")
    tid = str(uuid4())
    with store.connect() as db:
        modes = db.execute("SELECT mode FROM trials WHERE participant=?", (participant,)).fetchall()
        if any(r["mode"] != mode for r in modes):
            raise ValueError("Use one evidence mode per participant")
        existing = db.execute(
            "SELECT * FROM trials WHERE participant=? AND report_id=? AND condition=?",
            (participant, report_id, condition),
        ).fetchone()
        if existing:
            if existing["finished"]:
                raise ValueError("This assignment is already completed")
            return dict(existing)
        db.execute(
            "INSERT INTO trials(id,participant,report_id,condition,started,mode) VALUES(?,?,?,?,?,?)",
            (tid, participant, report_id, condition, now(), mode),
        )
        return dict(db.execute("SELECT * FROM trials WHERE id=?", (tid,)).fetchone())


def finish(store, tid, decision):
    if decision not in {"approve", "reject"}:
        raise ValueError("Invalid decision")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        sql = "SELECT * FROM trials WHERE id=?"
        if store.path.startswith("postgresql://"):
            sql += " FOR UPDATE"
        row = db.execute(sql, (tid,)).fetchone()
        if not row:
            raise KeyError(tid)
        if row["finished"]:
            raise ValueError("Trial already completed")
        end = now()
        seconds = max(
            0,
            (datetime.fromisoformat(end) - datetime.fromisoformat(row["started"])).total_seconds(),
        )
        db.execute(
            "UPDATE trials SET finished=?,seconds=?,decision=? WHERE id=?",
            (end, seconds, decision, tid),
        )
        return dict(db.execute("SELECT * FROM trials WHERE id=?", (tid,)).fetchone())


def summary(store):
    with store.connect() as db:
        trials = [dict(r) for r in db.execute("SELECT * FROM trials ORDER BY started")]
    complete = [r for r in trials if r["finished"]]
    groups = {}
    for r in complete:
        groups.setdefault((r["participant"], r["report_id"], r["mode"]), {})[r["condition"]] = r
    pairs = [p for p in groups.values() if "manual" in p and "assisted" in p]
    manual = median([p["manual"]["seconds"] for p in pairs]) if pairs else None
    assisted = median([p["assisted"]["seconds"] for p in pairs]) if pairs else None
    truth = json.loads((ROOT / "data/labels/flags.json").read_text())
    correct = sum((r["decision"] == "reject") == bool(truth[r["report_id"]]) for r in complete)
    return dict(
        completed_trials=len(complete),
        incomplete_trials=len(trials) - len(complete),
        paired_reports=len(pairs),
        participants=len({r["participant"] for r in complete}),
        manual_median_seconds=manual,
        assisted_median_seconds=assisted,
        reduction_percent=round(100 * (manual - assisted) / manual, 1) if manual else None,
        decision_agreement=correct / len(complete) if complete else None,
        measurement="human_trials" if complete else "not_measured",
        limitations="Self-timed local study; repeated-report learning and order effects. No production or causal time-saving claim.",
        trials=trials,
    )
