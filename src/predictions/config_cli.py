"""CLI to view and update scanner config stored in SQLite.

Usage (run from the repo root):
    uv run python -m predictions.config_cli                     # show all config
    uv run python -m predictions.config_cli set KEY VALUE       # set a config value
    uv run python -m predictions.config_cli set bet_percent 5
    uv run python -m predictions.config_cli set max_positions 30
    uv run python -m predictions.config_cli set stretch_price_min 85
    uv run python -m predictions.config_cli set final_seconds:soccer/eng.1 4800
    uv run python -m predictions.config_cli delete KEY          # remove override
    uv run python -m predictions.config_cli reset               # reset to defaults
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from predictions.db import (
    ConfigEntry,
    get_all_config,
    get_session,
    init_db,
    reset_all_config,
    set_config,
)


def show_config():
    cfg = get_all_config()

    # Group into categories
    trading = {}
    finals = {}
    other = {}

    for k, v in sorted(cfg.items()):
        if k.startswith("final_seconds:"):
            finals[k.removeprefix("final_seconds:")] = v
        elif k in (
            "bet_percent",
            "max_positions",
            "stretch_price_min",
        ):
            trading[k] = v
        else:
            other[k] = v

    print("\n=== Trading Parameters ===")
    for k, v in sorted(trading.items()):
        print(f"  {k:25s} = {v}")

    print("\n=== Final Minutes (seconds) by Sport ===")
    for sport, secs in sorted(finals.items()):
        s = int(secs)
        if s >= 60:
            desc = f"{s}s ({s // 60}m)"
        else:
            desc = f"{s}s"
        print(f"  {sport:40s} = {desc}")

    if other:
        print("\n=== Other ===")
        for k, v in sorted(other.items()):
            print(f"  {k:25s} = {v}")

    print()


def set_value(key: str, value: str):
    set_config(key, value)
    print(f"Set {key} = {value}")


def delete_key(key: str):
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    if entry:
        session.delete(entry)
        session.commit()
        print(f"Deleted {key} (will use default)")
    else:
        print(f"{key} not in DB (already using default)")
    session.close()


def reset_all():
    reset_all_config()
    print("All configuration overrides have been reset to match db.py defaults.")


if __name__ == "__main__":
    init_db()

    if len(sys.argv) == 1:
        show_config()
    elif sys.argv[1] == "set" and len(sys.argv) == 4:
        set_value(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "delete" and len(sys.argv) == 3:
        delete_key(sys.argv[2])
    elif sys.argv[1] == "reset" and len(sys.argv) == 2:
        reset_all()
    else:
        print(__doc__)
