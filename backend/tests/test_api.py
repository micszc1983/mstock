from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest


def test_health_endpoint(test_app):
    response = test_app.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_assets_endpoint_returns_seeded_assets(test_app):
    response = test_app.get("/assets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5
    assert any(item["id"] == "nvda" for item in data)


def test_dashboard_endpoint_returns_rows(test_app):
    response = test_app.get("/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert "trend_score" in data[0]


def test_thesis_endpoint_returns_payload(test_app):
    response = test_app.get("/assets/nvda/thesis")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "nvda"
    assert "thesis" in data
    assert "anti_thesis" in data


def test_manual_price_ingest(test_app):
    payload = {
        "timestamp": "2026-02-01T00:00:00+00:00",
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 12345,
    }
    response = test_app.post("/assets/nvda/prices", json=payload)
    assert response.status_code == 200
    assert response.json()["close"] == 103.0


def test_intraday_signals_summary_is_a_single_bulk_endpoint(test_app):
    response = test_app.get("/assets/intraday/signals-summary?resolution=15")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"] == "15"
    assert "nvda" in payload["signals"]
    assert payload["signals"]["nvda"] in {"BUY", "SELL", None}


def test_remote_paper_operations_do_not_require_admin_key(test_app):
    response = test_app.post(
        "/paper/accounts",
        json={"name": "phone-paper", "initial_cash": 16_000, "currency": "USD"},
    )

    assert response.status_code == 200
    assert response.json()["initial_cash"] == 16_000


def test_remote_admin_operations_still_require_admin_key(test_app):
    response = test_app.post("/admin/run-pipeline")

    assert response.status_code == 503
    assert "ADMIN_API_KEY" in response.json()["detail"]


def test_historical_portfolio_purchase_uses_session_close(test_app):
    prices_response = test_app.get("/assets/nvda/prices?limit=5000")
    assert prices_response.status_code == 200
    price = prices_response.json()[20]
    purchase_date = price["timestamp"][:10]
    invested_amount = 12_345.67

    response = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={
            "purchase_date": purchase_date,
            "invested_amount": invested_amount,
        },
    )

    assert response.status_code == 200
    position = response.json()
    assert position["purchase_date"] == purchase_date
    assert position["invested_amount"] == pytest.approx(invested_amount)
    assert position["avg_buy_price"] == pytest.approx(price["close"])
    assert position["quantity"] == pytest.approx(invested_amount / price["close"])

    listed = test_app.get("/portfolio/positions").json()
    assert listed == [position]


def test_historical_portfolio_purchase_accepts_exact_execution_price(test_app):
    response = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={
            "purchase_date": "2024-01-06",
            "invested_amount": 1_000,
            "purchase_price": 125,
        },
    )

    assert response.status_code == 200
    position = response.json()
    assert position["avg_buy_price"] == pytest.approx(125)
    assert position["quantity"] == pytest.approx(8)


def test_historical_portfolio_purchase_adds_lot_with_weighted_average(test_app):
    first = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={"purchase_date": "2024-01-05", "invested_amount": 1_000, "purchase_price": 100},
    )
    second = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={"purchase_date": "2024-02-05", "invested_amount": 600, "purchase_price": 120},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    position = second.json()
    assert position["quantity"] == pytest.approx(15)
    assert position["invested_amount"] == pytest.approx(1_600)
    assert position["avg_buy_price"] == pytest.approx(1_600 / 15)
    assert position["purchase_date"] == "2024-01-05"


def test_portfolio_position_can_be_fully_edited(test_app):
    created = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={"purchase_date": "2024-01-05", "invested_amount": 1_000, "purchase_price": 100},
    )
    assert created.status_code == 200

    response = test_app.patch(
        "/portfolio/positions/nvda",
        json={
            "asset_id": "aapl",
            "purchase_date": "2024-03-11",
            "quantity": 7.5,
            "avg_buy_price": 180,
        },
    )

    assert response.status_code == 200
    position = response.json()
    assert position["asset_id"] == "aapl"
    assert position["purchase_date"] == "2024-03-11"
    assert position["quantity"] == pytest.approx(7.5)
    assert position["avg_buy_price"] == pytest.approx(180)
    assert position["invested_amount"] == pytest.approx(1_350)
    assert [row["asset_id"] for row in test_app.get("/portfolio/positions").json()] == ["aapl"]


def test_portfolio_edit_rejects_duplicate_asset(test_app):
    for asset_id in ("nvda", "aapl"):
        response = test_app.post(
            f"/portfolio/positions/{asset_id}/historical-purchase",
            json={"purchase_date": "2024-01-05", "invested_amount": 1_000, "purchase_price": 100},
        )
        assert response.status_code == 200

    response = test_app.patch(
        "/portfolio/positions/nvda",
        json={"asset_id": "aapl", "purchase_date": "2024-01-05", "quantity": 10, "avg_buy_price": 100},
    )

    assert response.status_code == 409
    assert "już w portfelu" in response.json()["detail"]


def test_portfolio_valuation_is_always_returned_in_pln(test_app):
    created = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={"purchase_date": "2024-01-05", "invested_amount": 1_000, "purchase_price": 100},
    )
    assert created.status_code == 200

    response = test_app.get("/portfolio/valuations")

    assert response.status_code == 200
    valuation = response.json()[0]
    assert valuation["asset_id"] == "nvda"
    assert valuation["source_currency"] == "USD"
    assert valuation["fx_rate_to_pln"] == pytest.approx(1.0)
    assert valuation["last_price_pln"] == pytest.approx(valuation["last_price_source"])
    assert valuation["current_value_pln"] == pytest.approx(
        created.json()["quantity"] * valuation["last_price_pln"]
    )


def test_legacy_foreign_portfolio_cost_is_exposed_in_pln(monkeypatch):
    from app.api.routes import portfolio as portfolio_route
    from app.db.models import AssetORM

    class FakeDb:
        def get(self, model, asset_id):
            assert model is AssetORM
            assert asset_id == "nvda"
            return SimpleNamespace(currency="USD")

    purchase_date = date(2024, 1, 5)
    row = SimpleNamespace(
        asset_id="nvda",
        quantity=10.0,
        avg_buy_price=100.0,
        purchase_date=purchase_date,
        invested_amount=1_000.0,
        cost_currency=None,
        updated_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
    )
    calls = []

    def fake_to_pln(value, currency, on_date=None):
        calls.append((value, currency, on_date))
        return float(value) * 4.0

    monkeypatch.setattr(portfolio_route, "to_pln", fake_to_pln)

    response = portfolio_route._position_response(FakeDb(), row)

    assert response.avg_buy_price == pytest.approx(400.0)
    assert response.invested_amount == pytest.approx(4_000.0)
    assert response.cost_currency == "PLN"
    assert calls == [(1.0, "USD", purchase_date)]


def test_historical_portfolio_purchase_rejects_missing_market_price(test_app):
    response = test_app.post(
        "/portfolio/positions/nvda/historical-purchase",
        json={
            "purchase_date": "2024-01-06",
            "invested_amount": 1_000,
        },
    )

    assert response.status_code == 422
    assert "Brak notowania" in response.json()["detail"]
