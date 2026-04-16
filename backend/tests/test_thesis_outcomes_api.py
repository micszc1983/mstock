from __future__ import annotations


def test_rebuild_thesis_outcomes_endpoint(test_app):
    response = test_app.post("/assets/nvda/thesis-outcomes/rebuild")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "nvda"
    assert payload["evaluated"] >= 1


def test_get_thesis_outcomes_history_endpoint(test_app):
    test_app.post("/assets/nvda/thesis-outcomes/rebuild")
    response = test_app.get("/assets/nvda/thesis-outcomes/history")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert payload[0]["asset_id"] == "nvda"


def test_get_single_thesis_outcomes_endpoint(test_app):
    theses = test_app.get("/assets/nvda/theses/history")
    assert theses.status_code == 200
    thesis_rows = theses.json()
    assert len(thesis_rows) >= 1
    thesis_id = thesis_rows[0]["id"]

    rebuild = test_app.post("/assets/nvda/thesis-outcomes/rebuild")
    assert rebuild.status_code == 200

    response = test_app.get(f"/assets/nvda/theses/{thesis_id}/outcomes")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 1
    assert all(item["thesis_id"] == thesis_id for item in payload)
