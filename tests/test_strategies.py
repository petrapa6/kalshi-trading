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
        "      - sport: soccer/eng.1\n"
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
