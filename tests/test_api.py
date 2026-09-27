import json

from fastapi.testclient import TestClient

from auditor.api import create_app
from auditor.checks import audit, check_policy, convert_currency
from auditor.intake import fixture_intake
from auditor.store import Store


async def fake_call(url, payload):
    if "report_id" in payload:
        return fixture_intake(payload["report_id"])
    if "conversions" not in payload:
        converted = {
            e["id"]: convert_currency(e["amount"], e["currency"])
            for e in payload["report"]["expenses"]
        }
        return dict(payload, conversions=converted, **check_policy(payload["report"], converted))
    return audit(payload)


def start(client, id="run-1"):
    return client.post(
        "/agent",
        json=dict(
            threadId="report-01",
            runId=id,
            messages=[],
            tools=[],
            context=[],
            forwardedProps={"report_id": "report-01"},
        ),
    )


def test_agui_and_durable_review(tmp_path):
    db = tmp_path / "test.sqlite"
    with TestClient(create_app(db, fake_call)) as c:
        response = start(c)
        assert response.status_code == 200
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        assert events[0]["type"] == "RUN_STARTED"
        assert events[-1]["type"] == "RUN_FINISHED"
        assert [e["stepName"] for e in events if e["type"] == "STEP_FINISHED"] == [
            "intake",
            "policy",
            "audit",
        ]
        assert c.get("/api/runs/run-1").json()["status"] == "pending_review"
        assert (
            c.post(
                "/api/review", json=dict(run_id="run-1", action="approve", comment="Checked")
            ).status_code
            == 200
        )
        assert c.post("/api/review", json=dict(run_id="run-1", action="reject")).status_code == 409
        assert start(c).status_code == 409
    with TestClient(create_app(db, fake_call)) as c:
        stored = c.get("/api/runs/run-1").json()
        assert stored["status"] == "approved"
        assert stored["events"][-1]["body"]["comment"] == "Checked"
        assert (
            c.post(
                "/api/review", json=dict(run_id="run-1", action="comment", comment="Follow-up")
            ).status_code
            == 200
        )
        assert c.get("/api/receipts/r01").status_code == 200
        assert c.get("/api/receipts/nope").status_code == 404


def test_failed_run_cannot_be_approved(tmp_path):
    async def fail(url, payload):
        raise RuntimeError("sensitive provider details must not be streamed")

    with TestClient(create_app(tmp_path / "test.sqlite", fail)) as c:
        response = start(c)
        assert "RUN_ERROR" in response.text and "sensitive" not in response.text
        assert c.get("/api/runs/run-1").json()["status"] == "failed"
        assert c.post("/api/review", json=dict(run_id="run-1", action="approve")).status_code == 409
        assert (
            c.post("/api/review", json=dict(run_id="missing", action="approve")).status_code == 404
        )
        assert (
            c.post(
                "/agent",
                json=dict(
                    threadId="x",
                    runId="x",
                    messages=[],
                    tools=[],
                    context=[],
                    forwardedProps={"report_id": "../../secret"},
                ),
            ).status_code
            == 422
        )


def test_restart_marks_interrupted_run_failed(tmp_path):
    db = tmp_path / "test.sqlite"
    Store(db).start("interrupted", "report-01")
    with TestClient(create_app(db, fake_call)) as c:
        assert c.get("/api/runs/interrupted").json()["status"] == "failed"
