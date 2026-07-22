from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AssetORM
from app.db.session import Base
from app.seed import seed_database


def test_seed_updates_corrected_builtin_asset_metadata(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add(AssetORM(
            id="prc", symbol="PRC", name="Pracuj.pl", type="stock",
            currency="PLN", price_symbol="PRC.WA", news_term="Pracuj.pl rekrutacja",
        ))
        db.commit()

        seed_database(db)
        asset = db.get(AssetORM, "prc")
        assert asset.symbol == "GPP"
        assert asset.name == "Grupa Pracuj"
        assert asset.price_symbol == "GPP.WA"
        assert asset.news_term == "Grupa Pracuj"
