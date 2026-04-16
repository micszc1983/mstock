from __future__ import annotations


def test_get_latest_saved_thesis(test_app):
    response = test_app.get("/assets/nvda/theses/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert "source_snapshot_at" in payload
    assert "model_name" in payload


def test_get_thesis_history(test_app):
    response = test_app.get("/assets/nvda/theses/history?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert payload[0]["asset_id"] == "nvda"
