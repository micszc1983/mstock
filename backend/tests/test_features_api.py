from __future__ import annotations


def test_get_latest_features(test_app):
    response = test_app.get("/assets/nvda/features/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert "trend_score" in payload
    assert "volatility_10d" in payload


def test_get_feature_history(test_app):
    response = test_app.get("/assets/nvda/features/history?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert payload[0]["asset_id"] == "nvda"


def test_get_latest_forecast(test_app):
    response = test_app.get("/assets/nvda/forecast")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert {row["horizon"] for row in payload} == {"1d", "5d", "20d"}


def test_get_forecast_history(test_app):
    response = test_app.get("/assets/nvda/forecast/history?horizon=5d&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert all(row["horizon"] == "5d" for row in payload)


def test_rebuild_features_endpoint(test_app):
    response = test_app.post("/features/rebuild")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rebuilt_assets"] >= 1
