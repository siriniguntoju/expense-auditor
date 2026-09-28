"""Resumable Gemini extraction benchmark. No fixture fallback, no retries."""

import argparse
import asyncio
import json
from datetime import datetime, timezone

from auditor.live import MODEL, cache_path, enabled, extract_cached
from auditor.paths import ROOT
from evals.grading import extraction_metrics, line_item_metrics


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200, choices=range(1, 201))
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--delay", type=float, default=7, help="Seconds between new requests")
    args = parser.parse_args()
    if not args.cache_only and not enabled():
        parser.error(
            "Live calls disabled: configure GEMINI_API_KEY and confirm billing disabled with GEMINI_FREE_TIER_CONFIRMED=true."
        )
    truth = json.loads((ROOT / "data/labels/receipts.json").read_text())
    selected = dict(list(truth.items())[: args.limit])
    actual = {}
    errors = {}
    new_calls = 0

    def save():
        result = dict(
            generated_at=datetime.now(timezone.utc).isoformat(),
            model=MODEL,
            selected=len(selected),
            completed=len(actual),
            new_requests_this_run=new_calls,
            errors=errors,
            metrics=extraction_metrics(actual, selected),
            complete=len(actual) == len(selected),
            observed_completed_field_accuracy=extraction_metrics(
                actual, {k: selected[k] for k in actual}
            )["accuracy"],
            line_items=line_item_metrics(actual, selected),
            note="Missing/failed/unattempted selected receipts count as incorrect. Cached real model outputs are reused. No fixture fallback.",
            predictions=actual,
        )
        (ROOT / "results").mkdir(exist_ok=True)
        (ROOT / "results/live-extraction.json").write_text(json.dumps(result, indent=2) + "\n")
        public = {k: v for k, v in result.items() if k != "predictions"}
        (ROOT / "docs/live-extraction-results.json").write_text(json.dumps(public, indent=2) + "\n")
        return public

    for rid in selected:
        image = (ROOT / f"data/receipts/{rid}.png").read_bytes()
        is_new = not cache_path(image).exists()
        try:
            if is_new and not args.cache_only:
                if new_calls:
                    await asyncio.sleep(max(0, args.delay))
                new_calls += 1
            record = await extract_cached(image, cache_only=args.cache_only)
            actual[rid] = record["receipt"]
            save()
            print(f"{rid}: extracted ({len(actual)}/{len(selected)})", flush=True)
        except Exception as exc:
            errors[rid] = dict(type=type(exc).__name__, code=getattr(exc, "code", None))
            save()
            if not args.cache_only:
                break
    print(json.dumps(save(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
