"""Explicit optional Gemini benchmark. Not used by the demo or offline tests."""

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from auditor.intake import extract_image
from auditor.paths import ROOT
from evals.grading import extraction_metrics


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-free-tier",
        action="store_true",
        help="Confirm you verified billing is disabled; this program cannot verify your billing account.",
    )
    parser.add_argument("--limit", type=int, default=1, choices=range(1, 21))
    args = parser.parse_args()
    if not args.confirm_free_tier:
        parser.error(
            "Verify billing is disabled, then explicitly pass --confirm-free-tier. No calls made."
        )
    load_dotenv(ROOT / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        parser.error("Set GEMINI_API_KEY in your local .env. No calls made.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    truth = json.loads((ROOT / "data/labels/receipts.json").read_text())
    selected = dict(list(truth.items())[: args.limit])
    actual = {}
    errors = {}
    for rid in selected:
        try:
            result = await extract_image(
                (ROOT / f"data/receipts/{rid}.png").read_bytes(), model, key
            )
            actual[rid] = result.model_dump(mode="json")
        except Exception as exc:
            errors[rid] = type(exc).__name__
            break  # No retries or fallback paid models on quota/provider errors.
    output = dict(
        model=model,
        attempted=len(actual) + len(errors),
        completed=len(actual),
        selected=len(selected),
        errors=errors,
        metrics=extraction_metrics(actual, selected),
        predictions=actual,
        note="Unattempted and failed selected receipts count as missing; tiny synthetic set, not production accuracy.",
    )
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/live-extraction.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "predictions"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
