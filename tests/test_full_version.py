import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auditor import live, study
from auditor.api import create_app
from auditor.checks import audit, check_policy, convert_currency
from auditor.intake import fixture_intake, intake
from auditor.store import Store


async def test_cache_is_real_and_live_is_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "CACHE", tmp_path)
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    with pytest.raises(ValueError, match="requires"):
        await live.extract_cached(b"test")
    with pytest.raises(ValueError, match="No cached"):
        await live.extract_cached(b"test", cache_only=True)
    receipt = fixture_intake("report-01")["receipts"]["r01"]
    live.cache_path(b"test").write_text(json.dumps({"receipt": receipt, "model": "test"}))
    assert (await live.extract_cached(b"test", cache_only=True))["receipt"] == receipt
    assert live.cache_path(b"other") != live.cache_path(b"test")


async def test_live_intake_never_uses_ground_truth(monkeypatch):
    expected = fixture_intake("report-01")["receipts"]["r01"]
    expected = dict(expected, merchant="Model output merchant")

    async def fake(image, cache_only=False):
        return dict(receipt=expected, model="stub", image_sha256="stub", usage={})

    monkeypatch.setattr(live, "extract_cached", fake)
    packet = await intake("report-01", "gemini_live")
    assert packet["intake_mode"] == "gemini_live"
    assert all(r["merchant"] == "Model output merchant" for r in packet["receipts"].values())

    async def fail(*args, **kwargs):
        raise RuntimeError("quota")

    monkeypatch.setattr(live, "extract_cached", fail)
    with pytest.raises(RuntimeError):
        await intake("report-01", "gemini_live")


def test_daily_category_and_holiday_checks():
    packet = fixture_intake("report-01")
    for e in packet["report"]["expenses"]:
        e["category"] = "meals"
        e["amount"] = "60.00"
    conversions = {
        e["id"]: convert_currency(e["amount"], e["currency"]) for e in packet["report"]["expenses"]
    }
    result = check_policy(packet["report"], conversions, packet["receipts"])
    assert [f["rule"] for f in result["flags"]] == ["DAILY_MEAL_LIMIT"]
    packet = fixture_intake("report-01")
    packet["report"]["expenses"][0].update(category="lodging", amount="300.00")
    conversions = {
        e["id"]: convert_currency(e["amount"], e["currency"]) for e in packet["report"]["expenses"]
    }
    assert check_policy(packet["report"], conversions)["flags"][0]["rule"] == "CATEGORY_LIMIT"
    packet = fixture_intake("report-01")
    packet["receipts"]["r01"]["date"] = "2026-09-07"
    packet["conversions"] = conversions
    assert "HOLIDAY_REVIEW" in [f["rule"] for f in audit(packet)["flags"]]


def test_study_no_fabricated_results_and_paired_summary(tmp_path):
    store = Store(tmp_path / "study.sqlite")
    assert study.summary(store)["measurement"] == "not_measured"
    for condition, seconds in [("manual", 120), ("assisted", 60)]:
        trial = study.start(store, "TEST_ONLY", "report-01", condition, "fixture_replay")
        # Controlled timestamps exist only in the isolated temporary test DB.
        with store.connect() as db:
            db.execute(
                "UPDATE trials SET started=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(),
                    trial["id"],
                ),
            )
        study.finish(store, trial["id"], "approve")
        with pytest.raises(ValueError):
            study.finish(store, trial["id"], "reject")
    result = study.summary(store)
    assert result["paired_reports"] == 1
    assert result["reduction_percent"] == pytest.approx(50, abs=0.1)
    assert result["decision_agreement"] == 1


def test_study_api_blinds_manual_case_and_mode_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_FREE_TIER_CONFIRMED", raising=False)
    with TestClient(create_app(tmp_path / "api.sqlite")) as c:
        assert c.get("/api/study").json()["completed_trials"] == 0
        r = c.post(
            "/api/study/start",
            json=dict(participant="TEST_ONLY", report_id="report-03", condition="manual"),
        )
        assert r.status_code == 200
        assert r.json()["packet"] is None
        assert r.json()["report"]["title"] == "Study case 03"
        assert (
            c.post(
                "/agent",
                json=dict(
                    threadId="x",
                    runId="x",
                    messages=[],
                    tools=[],
                    context=[],
                    forwardedProps=dict(report_id="report-01", mode="gemini_live"),
                ),
            ).status_code
            == 409
        )
        assert c.get("/api/receipts/r200").status_code == 200
        assert c.get("/api/receipts/r201").status_code == 404


async def test_gemini_adapter_caches_validated_output_and_disables_retries(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(live, "CACHE", tmp_path)
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    calls = []
    receipt = fixture_intake("report-01")["receipts"]["r01"]

    async def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(receipt), usage_metadata=None)

    async def aclose():
        pass

    def factory(**kwargs):
        assert kwargs["http_options"].retry_options.attempts == 1
        return SimpleNamespace(
            aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate), aclose=aclose),
            close=lambda: None,
        )

    monkeypatch.setattr(live.genai, "Client", factory)
    first = await live.extract_cached(b"synthetic image")
    second = await live.extract_cached(b"synthetic image")
    assert first == second and len(calls) == 1
    assert calls[0]["config"].response_mime_type == "application/json"


async def test_a2a_returns_safe_cache_error(monkeypatch, tmp_path):
    import httpx

    from auditor.a2a_client import invoke
    from auditor.errors import AgentFailure
    from auditor.services.app import create_app as agent_app

    monkeypatch.setattr(live, "CACHE", tmp_path)
    app = agent_app("intake", "http://agent/")
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client,
    ):
        with pytest.raises(AgentFailure, match="missing from the cache"):
            await invoke(
                "http://agent/", {"report_id": "report-01", "mode": "gemini_cached"}, client
            )
