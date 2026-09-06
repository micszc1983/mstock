from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import AssetORM, NewsItemORM
from app.db.session import Base
from app.repositories.news import _clean_title, upsert_news_item
from app.schemas.common import NarrativeLabel
from app.schemas.news import NewsItem


def test_clean_title_removes_provider_zero_width_payload():
    assert _clean_title("  Important\u200b\u200c\u200d\ufeff news  ") == "Important news"


def test_upsert_news_deduplicates_same_provider_batch_before_flush(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(
            id="gold", symbol="GOLD", name="Gold", type="metal", currency="USD",
        ))
        db.commit()
        first = NewsItem(
            id="provider-duplicate",
            asset_id="gold",
            published_at=datetime.now(timezone.utc),
            source="provider",
            title="Pierwszy tytuł",
            body="body",
            sentiment_score=0.1,
            impact_score=0.5,
            narratives={NarrativeLabel.SAFE_HAVEN: 0.7},
        )
        updated = first.model_copy(update={"title": "Nowszy tytuł"})

        assert upsert_news_item(db, first) is True
        assert upsert_news_item(db, updated) is False
        db.commit()

        assert db.scalar(select(func.count()).select_from(NewsItemORM)) == 1
        assert db.get(NewsItemORM, first.id).title == "Nowszy tytuł"


def test_upsert_news_deduplicates_same_story_from_different_providers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cross-provider.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(AssetORM(id="pge", symbol="PGE", name="PGE", type="stock", currency="PLN"))
        db.commit()
        published = datetime.now(timezone.utc)
        first = NewsItem(
            id="pap-1", asset_id="pge", published_at=published, source="PAP",
            title="PGE podało wyniki finansowe za drugi kwartał",
            body="krótki opis", sentiment_score=0.1, impact_score=0.7,
            narratives={NarrativeLabel.DEMAND_STRENGTH: 0.6},
        )
        duplicate = first.model_copy(update={
            "id": "newsapi-2",
            "source": "newsapi",
            "title": "PGE podało wyniki finansowe za drugi kwartał - Bankier.pl",
            "body": "znacznie dłuższy opis tego samego raportu finansowego",
        })

        assert upsert_news_item(db, first) is True
        assert upsert_news_item(db, duplicate) is False
        db.commit()

        rows = db.scalars(select(NewsItemORM)).all()
        assert len(rows) == 1
        assert rows[0].body == duplicate.body
