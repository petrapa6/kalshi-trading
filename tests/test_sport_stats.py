import os
from predictions.db import init_db, get_session, Trade, StretchOpportunity

def run_test():
    # Setup test DB
    os.environ["DATABASE_URL"] = "sqlite:///test-sport-stats.db"
    
    if os.path.exists("test-sport-stats.db"):
        os.remove("test-sport-stats.db")
        
    init_db()
    session = get_session()
    
    # 1. Test MLB and MLBST separation handling
    print("Testing MLB/MLBST explicit separation logic...")
    
    # MLBST mock trade
    session.add(Trade(
        ticker="KXMLBSTGAME-TEST-BOS-NYY",
        status="settled_win",
        pnl_cents=100,
        dry_run=False,
    ))
    
    # MLB mock trade
    session.add(Trade(
        ticker="KXMLBGAME-TEST-BOS-NYY",
        status="settled_loss",
        pnl_cents=-50,
        dry_run=False,
    ))
    
    # Stretch opportunities mapped uniquely to series_ticker
    session.add(StretchOpportunity(
        ticker="KXMLBSTGAME-TEST-BOS-NYY",
        event_ticker="KXMLBSTGAME-TEST-BOS-NYY",
        series_ticker="KXMLBSTGAME",
        sport_path="baseball/mlb",
    ))
    session.add(StretchOpportunity(
        ticker="KXMLBGAME-MATCH-2-BOS-NYY",
        event_ticker="KXMLBGAME-MATCH-2-BOS-NYY",
        series_ticker="KXMLBGAME",
        sport_path="baseball/mlb",
    ))
    session.commit()
    
    from predictions.api import get_total_sport_stats
    stats = get_total_sport_stats()["stats"]
    
    mlb_stats = stats.get("MLB")
    mlbst_stats = stats.get("MLBST")
    
    print(f"MLB Stats: {mlb_stats}")
    print(f"MLBST Stats: {mlbst_stats}")
    
    assert "MLBST" in stats, "MLBST was incorrectly aggregated downstream."
    assert mlbst_stats["wins"] == 1
    assert mlbst_stats["pnl"] == 100
    assert mlbst_stats["played"] == 1
    
    assert "MLB" in stats, "MLB was incorrectly wiped downstream."
    assert mlb_stats["wins"] == 0
    assert mlb_stats["pnl"] == -50
    assert mlb_stats["played"] == 1
    
    print("-> Separation test passed cleanly!")

if __name__ == "__main__":
    run_test()
