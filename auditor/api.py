import asyncio
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from ag_ui.core import (
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from auditor import study
from auditor.a2a_client import invoke
from auditor.checks import POLICY, RATES, audit
from auditor.errors import AgentFailure
from auditor.intake import intake
from auditor.live import MODEL, enabled
from auditor.paths import ROOT, report_by_id, reports
from auditor.policy_agent import run_policy
from auditor.schema import Review
from auditor.store import Store

URLS = {
    role: os.getenv(f"{role.upper()}_URL", f"http://127.0.0.1:{8211 + i}/")
    for i, role in enumerate(["intake", "policy", "audit"])
}


def create_app(db_path=None, agent_call=invoke):
    store = Store(
        db_path
        or os.getenv("DATABASE_URL", os.getenv("AUDITOR_DB", str(ROOT / "results/auditor.sqlite")))
    )
    tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Synthetic Expense Auditor", lifespan=lifespan)
    app.state.store = store

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "selectable",
            "live_enabled": enabled(),
            "model": MODEL,
            "receipts": len(json.loads((ROOT / "data/labels/receipts.json").read_text())),
            "reports": len(reports()),
        }

    @app.get("/api/reports")
    def list_reports():
        return [r.model_dump(mode="json") for r in reports()]

    @app.get("/api/runs")
    def list_runs():
        return store.recent()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        result = store.get(run_id)
        if result is None:
            raise HTTPException(404, "Run not found")
        return result

    @app.get("/api/receipts/{receipt_id}")
    def receipt(receipt_id: str):
        # Enumerated allowlist: no arbitrary file paths or user uploads.
        if receipt_id not in json.loads((ROOT / "data/labels/receipts.json").read_text()):
            raise HTTPException(404, "Receipt not found")
        return FileResponse(ROOT / f"data/receipts/{receipt_id}.png", media_type="image/png")

    @app.post("/api/review")
    def review(body: Review):
        try:
            return store.review(body.run_id, body.action, body.comment)
        except KeyError:
            raise HTTPException(404, "Run not found")
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/agent")
    async def run(body: RunAgentInput):
        props = body.forwarded_props or {}
        if not isinstance(props, dict):
            raise HTTPException(422, "Invalid run options")
        report_id = props.get("report_id")
        mode = props.get("mode", "fixture_replay")
        if mode not in {"fixture_replay", "gemini_live", "gemini_cached"}:
            raise HTTPException(422, "Invalid mode")
        if mode == "gemini_live" and not enabled():
            raise HTTPException(
                409, "Live extraction is disabled until free-tier billing is confirmed"
            )
        if not isinstance(report_id, str) or report_by_id(report_id) is None:
            raise HTTPException(422, "Choose a known synthetic report")
        if not body.run_id or len(body.run_id) > 100:
            raise HTTPException(422, "Invalid run id")
        try:
            store.start(body.run_id, report_id)
        except (sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(409, "Run id already exists")
        queue = asyncio.Queue()

        async def emit(event):
            data = event.model_dump(mode="json", by_alias=True, exclude_none=True)
            store.event(body.run_id, data["type"], data)
            await queue.put(event)

        async def work():
            try:
                await emit(RunStartedEvent(threadId=body.thread_id, runId=body.run_id))
                packet = {"report_id": report_id, "mode": mode}
                for role, url in URLS.items():
                    await emit(StepStartedEvent(stepName=role))
                    packet = await agent_call(url, packet)
                    await emit(StepFinishedEvent(stepName=role))
                    await emit(StateSnapshotEvent(snapshot={"stage": role, "packet": packet}))
                store.finish(body.run_id, packet)
                await emit(RunFinishedEvent(threadId=body.thread_id, runId=body.run_id))
            except asyncio.CancelledError:
                store.fail(body.run_id)
                raise
            except Exception as exc:
                store.fail(body.run_id)
                await emit(
                    RunErrorEvent(
                        message=exc.safe_message
                        if isinstance(exc, AgentFailure)
                        else "An agent failed. Check that all three local services are running; retry with a new run.",
                        code="AGENT_FAILED",
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(work())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

        async def stream():
            encoder = EventEncoder()
            while (event := await queue.get()) is not None:
                yield encoder.encode(event)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    class StudyStart(BaseModel):
        participant: str = Field(pattern=r"^[A-Za-z0-9_-]{3,30}$")
        report_id: str
        condition: Literal["manual", "assisted"]
        mode: Literal["fixture_replay", "gemini_cached"] = "fixture_replay"

    class StudyFinish(BaseModel):
        decision: Literal["approve", "reject"]

    @app.get("/api/study")
    def study_state():
        return dict(study.summary(store), cases=study.CASES, policy=POLICY, rates=RATES)

    @app.post("/api/study/start")
    async def start_study(body: StudyStart):
        try:
            # Prepare assisted evidence BEFORE timing starts; model/service latency is separate.
            packet = None
            if body.condition == "assisted":
                packet = audit(await run_policy(await intake(body.report_id, body.mode)))
            trial = study.start(store, body.participant, body.report_id, body.condition, body.mode)
            report = report_by_id(body.report_id).model_dump(mode="json")
            report["title"] = "Study case " + body.report_id.rsplit("-", 1)[-1]
            if packet:
                packet["report"] = report
            return dict(trial=trial, report=report, packet=packet)
        except (ValueError, sqlite3.IntegrityError, UniqueViolation):
            raise HTTPException(
                409, "Assignment unavailable, already completed, or cached extraction missing"
            )

    @app.post("/api/study/{trial_id}/finish")
    def finish_study(trial_id: str, body: StudyFinish):
        try:
            return study.finish(store, trial_id, body.decision)
        except KeyError:
            raise HTTPException(404, "Trial not found")
        except ValueError as e:
            raise HTTPException(409, str(e))

    dist = ROOT / "web/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
