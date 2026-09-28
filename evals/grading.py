def key(flag):
    return flag["rule"], tuple(sorted(flag["lines"]))


def flag_metrics(actual, expected):
    true_positive = false_positive = false_negative = 0
    clean = clean_flagged = 0
    for report, labels in expected.items():
        wanted = {key(f) for f in labels}
        got = {key(f) for f in actual.get(report, [])}
        true_positive += len(wanted & got)
        false_positive += len(got - wanted)
        false_negative += len(wanted - got)
        if not wanted:
            clean += 1
            clean_flagged += bool(got)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "recall": true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else None,
        "precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None,
        "clean_reports": clean,
        "clean_reports_flagged": clean_flagged,
        "clean_report_false_positive_rate": clean_flagged / clean if clean else None,
    }


def extraction_metrics(actual, expected):
    fields = ["merchant", "date", "total", "currency", "category", "tax"]
    correct = 0
    total = len(expected) * len(fields)
    from decimal import Decimal, InvalidOperation

    for id, truth in expected.items():
        got = actual.get(id, {})
        for field in fields:
            if field not in got:
                continue
            if field in ("total", "tax"):
                try:
                    same = Decimal(str(got[field])) == Decimal(str(truth[field]))
                except (InvalidOperation, ValueError):
                    same = False
            else:
                same = str(got[field]).strip().casefold() == str(truth[field]).strip().casefold()
            correct += same
    return {
        "correct_fields": correct,
        "total_fields": total,
        "accuracy": correct / total if total else None,
        "fields": fields,
        "note": "Line-item extraction is not included in this field metric.",
    }


def line_item_metrics(actual, expected):
    """Exact normalized line-item lists; separate from the six core-field metric."""
    from decimal import Decimal, InvalidOperation

    correct = 0
    for rid, truth in expected.items():
        predicted = actual.get(rid, {}).get("items")
        if not isinstance(predicted, list):
            continue
        try:

            def normalize(items):
                return [
                    (" ".join(i["description"].casefold().split()), Decimal(str(i["amount"])))
                    for i in items
                ]

            correct += normalize(predicted) == normalize(truth["items"])
        except (KeyError, TypeError, InvalidOperation):
            pass
    return dict(
        exact_receipts=correct,
        total_receipts=len(expected),
        accuracy=correct / len(expected) if expected else None,
    )
