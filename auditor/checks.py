from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import yaml

from auditor.paths import ROOT
from auditor.schema import Receipt, Report

POLICY = yaml.safe_load((ROOT / "data/policy.yaml").read_text())
RATES = yaml.safe_load((ROOT / "data/rates.yaml").read_text())


def flag(rule, lines, explanation, evidence, severity="violation"):
    return dict(
        rule=rule, lines=lines, severity=severity, explanation=explanation, evidence=evidence
    )


def convert_currency(amount: str, currency: str) -> dict:
    if currency not in RATES["rates"]:
        raise ValueError("Unsupported currency")
    value = Decimal(amount)
    if not value.is_finite() or value < 0 or value > 1000000:
        raise ValueError("Invalid amount")
    rate = Decimal(RATES["rates"][currency])
    return dict(
        amount_usd=str((value * rate).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)),
        rate=str(rate),
        currency=currency,
        version=RATES["version"],
        as_of=RATES["as_of"],
    )


def check_policy(report: dict, conversions: dict, receipts: dict | None = None) -> dict:
    report = Report.model_validate(report)
    flags = []
    for e in report.expenses:
        usd = Decimal(conversions[e.id]["amount_usd"])
        evidence = dict(claim_usd=str(usd), policy_version=POLICY["version"])
        if e.category in POLICY["disallowed_categories"]:
            flags.append(flag("DISALLOWED", [e.id], "Alcohol is not reimbursable.", evidence))
        if e.category == "meals" and usd > Decimal(POLICY["meal_limit"]):
            flags.append(
                flag(
                    "MEAL_LIMIT",
                    [e.id],
                    "Meal exceeds the per-expense limit.",
                    dict(evidence, limit_usd=POLICY["meal_limit"]),
                )
            )
        if not e.receipt_id and usd > Decimal(POLICY["receipt_required_above"]):
            flags.append(
                flag(
                    "RECEIPT_REQUIRED",
                    [e.id],
                    "Receipt required above the threshold.",
                    dict(evidence, threshold_usd=POLICY["receipt_required_above"]),
                )
            )
    daily = defaultdict(list)
    for e in report.expenses:
        usd = Decimal(conversions[e.id]["amount_usd"])
        limit = POLICY.get("category_limits", {}).get(e.category)
        if limit and usd > Decimal(limit):
            flags.append(
                flag(
                    "CATEGORY_LIMIT",
                    [e.id],
                    "Category spending limit exceeded.",
                    dict(claim_usd=str(usd), limit_usd=limit, policy_version=POLICY["version"]),
                )
            )
        r = (receipts or {}).get(e.receipt_id)
        if r and e.category == "meals":
            daily[r["date"]].append(e)
    for day, expenses in daily.items():
        total = sum(Decimal(conversions[e.id]["amount_usd"]) for e in expenses)
        if total > Decimal(POLICY["meal_daily_limit"]):
            flags.append(
                flag(
                    "DAILY_MEAL_LIMIT",
                    [e.id for e in expenses],
                    "Daily meal allowance exceeded.",
                    dict(
                        date=day,
                        total_usd=str(total),
                        limit_usd=POLICY["meal_daily_limit"],
                        policy_version=POLICY["version"],
                    ),
                )
            )
    return dict(flags=flags, policy_version=POLICY["version"])


def audit(packet: dict) -> dict:
    report = Report.model_validate(packet["report"])
    flags = list(packet["flags"])
    groups, splits = defaultdict(list), defaultdict(list)
    for e in report.expenses:
        if not e.receipt_id:
            continue
        r = Receipt.model_validate(packet["receipts"][e.receipt_id])
        merchant = " ".join(r.merchant.casefold().split())
        groups[(merchant, str(r.date), str(r.total), r.currency)].append(e.id)
        if e.category == "meals":
            splits[(merchant, str(r.date))].append(e)
        if str(r.date) in POLICY.get("holidays", []):
            flags.append(
                flag(
                    "HOLIDAY_REVIEW",
                    [e.id],
                    "Synthetic policy holiday expense needs justification.",
                    dict(date=str(r.date), policy_version=POLICY["version"]),
                    "review",
                )
            )
        if r.date.weekday() >= 5:
            flags.append(
                flag(
                    "WEEKEND_REVIEW",
                    [e.id],
                    "Weekend expense needs a business explanation.",
                    dict(date=str(r.date)),
                    "review",
                )
            )
        if r.total != e.amount or r.currency != e.currency:
            flags.append(
                flag(
                    "AMOUNT_MISMATCH",
                    [e.id],
                    "Receipt and claimed amount/currency differ.",
                    dict(
                        receipt_total=str(r.total),
                        receipt_currency=r.currency,
                        claim=str(e.amount),
                        claim_currency=e.currency,
                    ),
                )
            )
        if r.category != e.category:
            flags.append(
                flag(
                    "CATEGORY_MISMATCH",
                    [e.id],
                    "Receipt and claim categories differ.",
                    dict(receipt_category=r.category, claim_category=e.category),
                )
            )
    for group, lines in groups.items():
        if len(lines) > 1:
            flags.append(
                flag(
                    "DUPLICATE",
                    lines,
                    "Matching merchant, date, total and currency.",
                    dict(fingerprint=list(group)),
                )
            )
    limit = Decimal(POLICY["meal_limit"])
    for (merchant, day), expenses in splits.items():
        amounts = [Decimal(packet["conversions"][e.id]["amount_usd"]) for e in expenses]
        if len(expenses) > 1 and all(a <= limit for a in amounts) and sum(amounts) > limit:
            flags.append(
                flag(
                    "SPLIT_REVIEW",
                    [e.id for e in expenses],
                    "Same-day meals at one merchant exceed the limit together.",
                    dict(merchant=merchant, date=day, combined_usd=str(sum(amounts))),
                    "review",
                )
            )
    return dict(packet, flags=flags, audit_version="deterministic-v1")
