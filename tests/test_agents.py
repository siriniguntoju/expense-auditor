import httpx
import pytest

from auditor.a2a_client import invoke
from auditor.checks import audit, check_policy, convert_currency
from auditor.intake import fixture_intake
from auditor.services.app import create_app


async def test_real_a2a_adk_mcp_pipeline():
    packet = {"report_id": "report-03"}
    for role in ["intake", "policy", "audit"]:
        app = create_app(role, "http://agent/")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://agent"
            ) as client,
        ):
            packet = await invoke("http://agent/", packet, client)
    assert [f["rule"] for f in packet["flags"]] == ["MEAL_LIMIT"]
    assert packet["conversions"]["e05"]["version"] == "synthetic-rates-v1"


@pytest.mark.parametrize(
    "amount,currency,expected",
    [("10", "EUR", "11.00"), ("10", "GBP", "12.50"), ("0.01", "GBP", "0.01")],
)
def test_rates(amount, currency, expected):
    assert convert_currency(amount, currency)["amount_usd"] == expected


@pytest.mark.parametrize("amount,currency", [("NaN", "USD"), ("-1", "USD"), ("1", "XXX")])
def test_invalid_rates(amount, currency):
    with pytest.raises(ValueError):
        convert_currency(amount, currency)


def test_policy_thresholds():
    packet = fixture_intake("report-01")
    e = packet["report"]["expenses"][0]
    e.update(amount="75.00", receipt_id=None)
    conversions = {
        x["id"]: convert_currency(x["amount"], x["currency"]) for x in packet["report"]["expenses"]
    }
    flags = check_policy(packet["report"], conversions)["flags"]
    assert [f["rule"] for f in flags] == ["RECEIPT_REQUIRED"]
    e["amount"] = "25.00"
    conversions[e["id"]] = convert_currency("25", "USD")
    assert check_policy(packet["report"], conversions)["flags"] == []


def test_currency_mismatch_and_category_mismatch():
    packet = fixture_intake("report-01")
    packet["report"]["expenses"][0].update(currency="EUR", category="transport")
    packet["conversions"] = {
        e["id"]: convert_currency(e["amount"], e["currency"]) for e in packet["report"]["expenses"]
    }
    assert {f["rule"] for f in audit(packet)["flags"]} == {"AMOUNT_MISMATCH", "CATEGORY_MISMATCH"}
