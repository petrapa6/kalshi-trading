"""Per-sport stats aggregation — MLB / MLBST must be kept distinct."""

from predictions.api import get_total_sport_stats
from predictions.db import StretchOpportunity, Trade, get_session


def test_mlb_and_mlbst_are_kept_distinct():
    session = get_session()

    session.add(
        Trade(
            ticker="KXMLBSTGAME-TEST-BOS-NYY",
            status="settled_win",
            pnl_cents=100,
            dry_run=False,
        )
    )
    session.add(
        Trade(
            ticker="KXMLBGAME-TEST-BOS-NYY",
            status="settled_loss",
            pnl_cents=-50,
            dry_run=False,
        )
    )
    session.add(
        StretchOpportunity(
            ticker="KXMLBSTGAME-TEST-BOS-NYY",
            event_ticker="KXMLBSTGAME-TEST-BOS-NYY",
            series_ticker="KXMLBSTGAME",
            sport_path="baseball/mlb",
        )
    )
    session.add(
        StretchOpportunity(
            ticker="KXMLBGAME-MATCH-2-BOS-NYY",
            event_ticker="KXMLBGAME-MATCH-2-BOS-NYY",
            series_ticker="KXMLBGAME",
            sport_path="baseball/mlb",
        )
    )
    session.commit()
    session.close()

    stats = get_total_sport_stats()["stats"]

    assert "MLBST" in stats, "MLBST was aggregated into a sibling sport"
    assert stats["MLBST"]["wins"] == 1
    assert stats["MLBST"]["pnl"] == 100
    assert stats["MLBST"]["played"] == 1

    assert "MLB" in stats, "MLB was wiped by downstream aggregation"
    assert stats["MLB"]["wins"] == 0
    assert stats["MLB"]["pnl"] == -50
    assert stats["MLB"]["played"] == 1
