"""Expand the original development suite to 200 receipts / 50 reports.
Templates are rendered with Pillow, with companion HTML for inspection.
This is synthetic regression coverage, not an independent held-out corpus.
"""

import copy
import html
import json
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from auditor.paths import ROOT
from data.generate import generate


def main():
    original, truth, labels = generate()
    reports = list(original)
    for j in range(11, 51):
        template = original[(j - 11) % 10]
        report = copy.deepcopy(template)
        report.update(
            id=f"report-{j:02}",
            employee=f"Employee Example {j}",
            title=f"{template['title']} · {j}",
        )
        mapping = {}
        for k, e in enumerate(report["expenses"]):
            i = 21 + (j - 11) * 4 + k
            old = e["id"]
            rid = f"r{i:02}"
            source = truth[template["expenses"][k]["receipt_id"] or "r07"]
            r = copy.deepcopy(source)
            r["merchant"] += f" / branch {j}"
            truth[rid] = r
            mapping[old] = f"e{i:02}"
            e.update(id=f"e{i:02}", receipt_id=rid if e["receipt_id"] else None)
        for k in [2, 3]:
            i = 21 + (j - 11) * 4 + k
            rid = f"r{i:02}"
            total = Decimal(12 + (j + k) % 12)
            truth[rid] = dict(
                merchant=f"Example Transit {i}",
                date="2026-09-23",
                total=str(total),
                currency="USD",
                category="transport",
                tax="1.00",
                items=[dict(description="Train ticket", amount=str(total - 1))],
            )
            report["expenses"].append(
                dict(
                    id=f"e{i:02}",
                    receipt_id=rid,
                    amount=str(total),
                    currency="USD",
                    category="transport",
                    justification="Synthetic business trip",
                )
            )
        labels[report["id"]] = [
            dict(rule=f["rule"], lines=[mapping[line] for line in f["lines"]])
            for f in labels[template["id"]]
        ]
        reports.append(report)
    # Twenty additional extraction-only receipts diversify currencies and typography.
    for i in range(181, 201):
        truth[f"r{i}"] = dict(
            merchant=f"Example Hotel {i}",
            date="2026-09-24",
            total="110.00",
            currency=["USD", "EUR", "GBP"][i % 3],
            category="lodging",
            tax="10.00",
            items=[dict(description="Room night", amount="100.00")],
        )
    dest = ROOT / "data/templates"
    dest.mkdir(exist_ok=True)
    for n, (rid, r) in enumerate(truth.items()):
        # Preserve original 20 images so previously measured results stay reproducible.
        if n < 20:
            continue
        style = n % 4
        width, height = (700, 850) if style % 2 else (760, 820)
        im = Image.new("RGB", (width, height), ["#fff", "#fbf6e9", "#f2f6fb", "#fff"][style])
        draw = ImageDraw.Draw(im)
        font = ImageFont.load_default(size=23 + style)
        x = 40 + style * 12
        lines = [
            "SYNTHETIC RECEIPT",
            r["merchant"],
            r["date"],
            "Receipt " + rid,
            "",
            *[f"{item['description']}  {item['amount']}" for item in r["items"]],
            "Tax " + r["tax"],
            "TOTAL " + r["total"] + " " + r["currency"],
            "Category: " + r["category"],
            "",
            "Fictional data / no payment",
        ]
        for k, line in enumerate(lines):
            draw.text((x, 45 + k * 52), line, font=font, fill="#202433")
        if n % 3 == 0:
            im = im.rotate(1.5, fillcolor="#e6e4dd")
        if n % 4 == 0:
            im = im.filter(ImageFilter.GaussianBlur(0.55))
        if n % 7 == 0:
            draw = ImageDraw.Draw(im)
            for xline in [190, 385]:
                draw.line((xline, 0, xline + 12, height), fill="#d5d3d0", width=1)
        im.save(ROOT / f"data/receipts/{rid}.png")
        (dest / f"{rid}.html").write_text(
            '<!doctype html><html><meta charset="utf-8"><title>Synthetic receipt</title><body><pre>'
            + html.escape("\n".join(lines))
            + "</pre></body></html>"
        )
    (ROOT / "data/reports.json").write_text(json.dumps(reports, indent=2) + "\n")
    (ROOT / "data/labels/receipts.json").write_text(json.dumps(truth, indent=2) + "\n")
    (ROOT / "data/labels/flags.json").write_text(json.dumps(labels, indent=2) + "\n")
    print(
        f"{len(truth)} receipts, {len(reports)} reports; 20 receipts reserved for extraction only"
    )


if __name__ == "__main__":
    main()
