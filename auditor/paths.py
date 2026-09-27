import json
from pathlib import Path

from auditor.schema import Report

ROOT = Path(__file__).resolve().parents[1]


def reports():
    return [Report.model_validate(x) for x in json.loads((ROOT / "data/reports.json").read_text())]


def report_by_id(report_id):
    return next((r for r in reports() if r.id == report_id), None)
