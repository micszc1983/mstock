from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import AssetORM, NewsItemORM, NewsNLPRunORM
from app.db.session import Base
from app.services.news_features import list_news_for_analysis


def test_analysis_uses_only_enriched_relevant_news(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'analysis-news.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        db.add(AssetORM(id="abc", symbol="ABC", name="ABC", type="stock", currency="USD"))
        for news_id, title in (("good", "ABC raises guidance"), ("noise", "Unrelated market summary"), ("raw", "ABC raw item")):
            db.add(NewsItemORM(
                id=news_id, asset_id="abc", published_at=now, source="wire",
                title=title, body="", sentiment_score=-1.0, impact_score=0.8,
            ))
        db.add_all([
            NewsNLPRunORM(
                news_id="good", model_name="model", processed_at=now,
                sentiment_score=0.75, sentiment_label="positive", sentiment_confidence=0.8,
                relevance_score=0.9, raw_output_json="{}",
            ),
            NewsNLPRunORM(
                news_id="noise", model_name="model", processed_at=now,
                sentiment_score=0.9, sentiment_label="positive", sentiment_confidence=0.9,
                relevance_score=0.1, raw_output_json="{}",
            ),
        ])
        db.commit()

        rows = list_news_for_analysis(db, "abc", as_of=now, min_relevance=0.35)

        assert [row.id for row in rows] == ["good"]
        assert rows[0].sentiment_score == 0.75
        assert rows[0].impact_score == 0.8 * 0.9 * 0.8
