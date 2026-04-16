from __future__ import annotations


def test_thesis_quality_summary_endpoint(test_app):
    test_app.post("/assets/nvda/thesis-outcomes/rebuild")
    response = test_app.get("/assets/nvda/quality/thesis/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert "directional_accuracy" in payload


def test_thesis_quality_by_horizon_endpoint(test_app):
    test_app.post("/assets/nvda/thesis-outcomes/rebuild")
    response = test_app.get("/assets/nvda/quality/thesis/by-horizon")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert "horizon" in payload[0]


def test_forecast_quality_summary_endpoint(test_app):
    response = test_app.get("/assets/nvda/quality/forecast/summary")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert payload[0]["asset_id"] == "nvda"
