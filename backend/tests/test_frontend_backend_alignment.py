from __future__ import annotations


def test_forecast_history_endpoint_exists(test_app):
    response = test_app.get("/assets/nvda/forecast/history")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)


def test_frontend_required_endpoints_exist(test_app):
    endpoints = [
        "/assets",
        "/assets/nvda/theses/latest",
        "/assets/nvda/forecast",
        "/assets/nvda/forecast/history",
        "/assets/nvda/thesis-outcomes/history",
        "/assets/nvda/quality/thesis/summary",
        "/assets/nvda/quality/thesis/by-horizon",
        "/assets/nvda/quality/forecast/summary",
        "/assets/nvda/narratives?days=14",
    ]
    for endpoint in endpoints:
        response = test_app.get(endpoint)
        assert response.status_code == 200, f"{endpoint} -> {response.status_code}"
