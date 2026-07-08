"""Tests for the YAML strategy loader (src/predictions/strategies.py)."""


def test_load_empty_file(tmp_path):
    """STR-01: an empty file logs a warning and returns []."""
    from predictions.strategies import load_strategies

    f = tmp_path / "empty.yaml"
    f.write_text("")
    result = load_strategies(str(f))
    assert result == []


def test_missing_file_returns_empty():
    """STR-01: a missing file logs a warning and returns []."""
    from predictions.strategies import load_strategies

    result = load_strategies("/nonexistent/strategies.yaml")
    assert result == []


def test_valid_file_loads(tmp_path):
    """STR-01: a well-formed file produces a non-empty list."""
    from predictions.strategies import load_strategies

    f = tmp_path / "valid.yaml"
    f.write_text(
        "strategies:\n"
        "  s:\n"
        "    triggers:\n"
        "      - sport: football\n"
        "        min_minute: 80\n"
        "        min_lead: 2\n"
    )
    result = load_strategies(str(f))
    assert len(result) == 1
    assert result[0].name == "s"


def test_strategies_path_env(tmp_path, monkeypatch):
    """STR-01 / D-08: STRATEGIES_PATH env var overrides the default path."""
    from predictions.strategies import load_strategies

    f = tmp_path / "from_env.yaml"
    f.write_text("strategies:\n  envstrat:\n    triggers:\n      - min_lead: 2\n")
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    result = load_strategies()  # no path argument — must read env
    assert len(result) == 1
    assert result[0].name == "envstrat"


def test_empty_triggers_rejected(tmp_path):
    """STR-02: triggers: [] must be rejected (min_length=1)."""
    from predictions.strategies import load_strategies

    f = tmp_path / "empty_triggers.yaml"
    f.write_text("strategies:\n  broken:\n    triggers: []\n")
    result = load_strategies(str(f))
    assert result == []


def test_unknown_field_rejected(tmp_path):
    """STR-02 / D-06: extra="forbid" rejects unknown fields (typos)."""
    from predictions.strategies import load_strategies

    f = tmp_path / "typo.yaml"
    f.write_text(
        "strategies:\n  s:\n    triggers:\n      - min_minutes: 80\n"  # typo: extra "s"
    )
    result = load_strategies(str(f))
    assert result == []


def test_one_bad_strategy_rejects_file(tmp_path):
    """D-07: any error in any strategy rejects the entire file."""
    from predictions.strategies import load_strategies

    f = tmp_path / "mixed.yaml"
    f.write_text(
        "strategies:\n"
        "  ok:\n"
        "    triggers:\n"
        "      - min_lead: 2\n"
        "  bad:\n"
        "    triggers:\n"
        "      - min_minutes: 80\n"  # typo
    )
    result = load_strategies(str(f))
    assert result == []  # entire file rejected, NOT just the bad strategy


def test_accepts_new_trigger_fields_and_live_flag(tmp_path):
    """Issue #13: sport_path + final_minutes + min_volume + live all parse."""
    from predictions.strategies import load_strategies

    f = tmp_path / "new_fields.yaml"
    f.write_text(
        "strategies:\n"
        "  s:\n"
        "    live: true\n"
        "    triggers:\n"
        "      - sport_path: hockey/nhl\n"
        "        final_minutes: true\n"
        "        min_volume: 200\n"
    )
    result = load_strategies(str(f))
    assert len(result) == 1
    strat = result[0]
    assert strat.live is True
    trig = strat.triggers[0]
    assert trig.sport_path == "hockey/nhl"
    assert trig.final_minutes is True
    assert trig.min_volume == 200


def test_live_defaults_false(tmp_path):
    """Issue #13: live is opt-in — absent means false."""
    from predictions.strategies import load_strategies

    f = tmp_path / "no_live.yaml"
    f.write_text("strategies:\n  s:\n    triggers:\n      - min_lead: 2\n")
    result = load_strategies(str(f))
    assert result[0].live is False


def test_unknown_sport_path_rejected(tmp_path):
    """Issue #13: a sport_path outside the registry rejects the file."""
    from predictions.strategies import load_strategies

    f = tmp_path / "bad_path.yaml"
    f.write_text(
        "strategies:\n  s:\n    triggers:\n      - sport_path: hockey/khl\n"  # not in registry
    )
    result = load_strategies(str(f))
    assert result == []


def test_non_bool_live_rejected(tmp_path):
    """Issue #13: live must be a real bool — a string/int rejects the file."""
    from predictions.strategies import load_strategies

    f = tmp_path / "bad_live.yaml"
    f.write_text(
        "strategies:\n  s:\n    live: 1\n    triggers:\n      - min_lead: 2\n"  # int, not bool
    )
    result = load_strategies(str(f))
    assert result == []


def test_yaml_safe_load_rejects_python_object_tags(tmp_path):
    """T-02-03: yaml.safe_load (not yaml.load) prevents arbitrary code via !!python/object."""
    from predictions.strategies import load_strategies

    f = tmp_path / "evil.yaml"
    f.write_text(
        "strategies:\n"
        "  evil:\n"
        "    triggers:\n"
        '      - sport: !!python/object/apply:os.system ["echo pwned"]\n'
    )
    # safe_load raises a ConstructorError for !!python tags; loader catches and returns []
    result = load_strategies(str(f))
    assert result == []
