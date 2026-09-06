from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AssetORM
from app.db.session import Base
from app.seed import seed_database
from app.asset_registry import ASSET_MAP
from app.services.earnings_service import _should_sync_earnings


def test_requested_etfs_have_verified_provider_symbols():
    expected = {
        "nucl": ("NUCL", "NUCL.L", "USD"),
        "wdef": ("WDEF", "EUDF.L", "USD"),
        "copx": ("COPX", "COPX", "USD"),
        "gdxj": ("GDXJ", "GDXJ", "USD"),
    }

    for asset_id, (symbol, price_symbol, currency) in expected.items():
        asset = ASSET_MAP[asset_id]
        assert (asset.symbol, asset.price_symbol, asset.currency) == (
            symbol, price_symbol, currency,
        )
        assert asset.sector is not None and asset.sector.startswith("ETF")


def test_etf_sector_is_excluded_from_earnings_sync():
    etf = AssetORM(
        id="nucl", symbol="NUCL", name="NUCL", type="stock",
        currency="USD", sector="ETF / Uranium & Nuclear", price_symbol="NUCL.L",
    )

    assert _should_sync_earnings(etf) is False


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
