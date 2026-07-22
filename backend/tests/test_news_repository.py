from app.repositories.news import _clean_title


def test_clean_title_removes_provider_zero_width_payload():
    assert _clean_title("  Important\u200b\u200c\u200d\ufeff news  ") == "Important news"
