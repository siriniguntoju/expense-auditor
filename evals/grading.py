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
