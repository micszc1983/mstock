from __future__ import annotations


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
