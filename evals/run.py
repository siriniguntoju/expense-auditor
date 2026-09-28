"""Offline end-to-end protocol benchmark; never invokes a model."""

import argparse
import asyncio
import json
import time

import httpx

from auditor.a2a_client import invoke
from auditor.paths import ROOT, reports
from auditor.services.app import create_app
from evals.grading import flag_metrics


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["fixture_replay", "gemini_cached"], default="fixture_replay"
    )
    args = parser.parse_args()
    started = time.perf_counter()
    actual, errors = {}, {}
    for report in reports():
        packet = {"report_id": report.id, "mode": args.mode}
        try:
            for role in ["intake", "policy", "audit"]:
                app = create_app(role, "http://agent/")
                async with (
                    app.router.lifespan_context(app),
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://agent",
                        timeout=90,
                    ) as client,
                ):
                    packet = await invoke("http://agent/", packet, client)
            actual[report.id] = packet["flags"]
        except Exception as e:
            errors[report.id] = type(e).__name__
    expected = json.loads((ROOT / "data/labels/flags.json").read_text())
    result = dict(
        mode=args.mode,
        model_calls=0,
        reports_total=len(expected),
        reports_completed=len(actual),
        errors=errors,
        extraction_accuracy="not_measured",
        human_review_time="not_measured",
        wall_seconds=round(time.perf_counter() - started, 2),
        metrics=flag_metrics(actual, expected),
        flags=actual,
    )
    (
        ROOT
        / (
            "docs/offline-results.json"
            if args.mode == "fixture_replay"
            else "docs/cached-gemini-results.json"
        )
    ).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "flags"}, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
