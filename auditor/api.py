import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

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

from auditor.a2a_client import invoke
from auditor.paths import ROOT, report_by_id, reports
from auditor.schema import Review
from auditor.store import Store

URLS = {
    role: os.getenv(f"{role.upper()}_URL", f"http://127.0.0.1:{8211 + i}/")
    for i, role in enumerate(["intake", "policy", "audit"])
}


def create_app(db_path=None, agent_call=invoke):
    store = Store(db_path or os.getenv("AUDITOR_DB", str(ROOT / "results/auditor.sqlite")))
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
        return {"status": "ok", "mode": "fixture_replay"}

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
        if receipt_id not in {f"r{i:02}" for i in range(1, 21)}:
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
        report_id = (body.forwarded_props or {}).get("report_id")
        if not isinstance(report_id, str) or report_by_id(report_id) is None:
            raise HTTPException(422, "Choose a known synthetic report")
        if not body.run_id or len(body.run_id) > 100:
            raise HTTPException(422, "Invalid run id")
        try:
            store.start(body.run_id, report_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Run id already exists")
        queue = asyncio.Queue()

        async def emit(event):
            data = event.model_dump(mode="json", by_alias=True, exclude_none=True)
            store.event(body.run_id, data["type"], data)
            await queue.put(event)

        async def work():
            try:
                await emit(RunStartedEvent(threadId=body.thread_id, runId=body.run_id))
                packet = {"report_id": report_id}
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
            except Exception:
                store.fail(body.run_id)
                await emit(
                    RunErrorEvent(
                        message="An agent failed. Check that all three local services are running; retry with a new run.",
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

    dist = ROOT / "web/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
