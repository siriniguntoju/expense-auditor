"""Twenty fictional receipt PNGs and ten reports. No OCR ground truth is inferred."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def generate():
    truth = {}
    reports = []
    titles = [
        "City visit · clean",
        "Client visit · clean",
        "Meal over limit",
        "Receipt missing",
        "Disallowed purchase",
        "Duplicate expense",
        "Possible split charge",
        "Weekend purchase",
        "Claim mismatch",
        "Currency conversion · clean",
    ]
    for i in range(1, 21):
        odd = i % 2 == 1
        truth[f"r{i:02}"] = {
            "merchant": f"Example {'Cafe' if odd else 'Transit'} {i}",
            "date": "2026-09-22",
            "total": "20.00" if odd else "15.00",
            "currency": "USD",
            "category": "meals" if odd else "transport",
            "tax": "2.00",
            "items": [
                {
                    "description": "Synthetic business purchase",
                    "amount": "18.00" if odd else "13.00",
                }
            ],
        }
    truth["r05"]["total"] = "90.00"
    truth["r05"]["items"][0]["amount"] = "88.00"
    truth["r07"]["total"] = "30.00"
    truth["r07"]["items"][0]["amount"] = "28.00"
    truth["r09"]["category"] = "alcohol"
    truth["r12"] = json.loads(json.dumps(truth["r11"]))
    for name in ["r13", "r14"]:
        truth[name].update(merchant="Example Split Cafe", category="meals", total="40.00")
        truth[name]["items"][0]["amount"] = "38.00"
    truth["r15"]["date"] = "2026-09-26"
    truth["r17"]["total"] = "45.00"
    truth["r17"]["items"][0]["amount"] = "43.00"
    truth["r19"]["currency"] = "EUR"
    truth["r20"]["currency"] = "GBP"
    for j in range(10):
        expenses = []
        for i in [j * 2 + 1, j * 2 + 2]:
            r = truth[f"r{i:02}"]
            expenses.append(
                {
                    "id": f"e{i:02}",
                    "receipt_id": None if i == 7 else f"r{i:02}",
                    "amount": "60.00" if i == 17 else r["total"],
                    "currency": r["currency"],
                    "category": r["category"],
                    "justification": "Fictional business travel",
                }
            )
        reports.append(
            {
                "id": f"report-{j + 1:02}",
                "employee": f"Employee Example {j + 1}",
                "title": titles[j],
                "expenses": expenses,
            }
        )
    expected = {f"report-{j:02}": [] for j in range(1, 11)}
    for report, rule, lines in [
        (3, "MEAL_LIMIT", ["e05"]),
        (4, "RECEIPT_REQUIRED", ["e07"]),
        (5, "DISALLOWED", ["e09"]),
        (6, "DUPLICATE", ["e11", "e12"]),
        (7, "SPLIT_REVIEW", ["e13", "e14"]),
        (8, "WEEKEND_REVIEW", ["e15"]),
        (9, "AMOUNT_MISMATCH", ["e17"]),
    ]:
        expected[f"report-{report:02}"].append({"rule": rule, "lines": lines})
    (ROOT / "data/labels/receipts.json").write_text(json.dumps(truth, indent=2) + "\n")
    (ROOT / "data/reports.json").write_text(json.dumps(reports, indent=2) + "\n")
    (ROOT / "data/labels/flags.json").write_text(json.dumps(expected, indent=2) + "\n")
    for n, (id, r) in enumerate(truth.items()):
        im = Image.new("RGB", (640, 760), "#f9f6ee" if n % 2 else "#ffffff")
        draw = ImageDraw.Draw(im)
        big = ImageFont.load_default(size=28)
        small = ImageFont.load_default(size=20)
        draw.text((48, 38), "SYNTHETIC RECEIPT", fill="#344551", font=big)
        lines = [
            r["merchant"],
            r["date"],
            "Receipt " + id,
            "-" * 31,
            r["items"][0]["description"],
            "Subtotal " + r["items"][0]["amount"],
            "Tax " + r["tax"],
            "TOTAL " + r["total"] + " " + r["currency"],
            "Category: " + r["category"],
            "-" * 31,
            "Fictional data / no payment",
            "Expense Auditor demo",
        ]
        for k, line in enumerate(lines):
            draw.text((48, 110 + k * 43), line, fill="#263238", font=small)
        if n % 5 == 1:
            im = im.rotate(1.2, fillcolor="#e8e5dd")
        if n % 5 == 2:
            im = im.filter(ImageFilter.GaussianBlur(0.4))
        im.save(ROOT / "data/receipts" / f"{id}.png")
    return reports, truth, expected


if __name__ == "__main__":
    generate()
