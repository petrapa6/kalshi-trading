"""YAML strategy loader and validation models.

Single boundary for parsing strategies.yaml. All callers receive
typed `Strategy` objects; nothing else in the codebase touches raw
YAML or untyped dicts.

Validation is strict and all-or-nothing: any error in any strategy
returns an empty list and logs a WARNING.
"""

import logging
import os
from typing import Annotated, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from predictions.sports import SPORT_BY_PATH

log = logging.getLogger(__name__)


class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sport: Optional[str] = None
    # Sport path: ESPN's fine-grained sport/league id (e.g. hockey/nhl),
    # narrower than `sport`. Implies its family.
    sport_path: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    # Final minutes: final period past the sport's end-of-game clock
    # threshold. Clock semantics come from the sport registry; undefined
    # (never matches) for clockless sports.
    final_minutes: Optional[bool] = None
    min_volume: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None

    @field_validator("sport_path")
    @classmethod
    def _known_sport_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SPORT_BY_PATH:
            raise ValueError(f"unknown sport path {v!r} — not in the sport registry")
        return v


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `name` is injected by load_strategies() from the YAML dict key.
    # It is not present in the YAML body and the strict-extras config does
    # not complain because the loader post-processes parsed strategies.
    name: str = ""
    description: Optional[str] = None
    # Live-enabled: opts the strategy into real-money placement. Parsed
    # here; gating lands in the unified-placement slice. Strict bool so a
    # stray int/string is a load error, not a silent truthy coercion.
    live: bool = Field(default=False, strict=True)
    triggers: Annotated[list[Trigger], Field(min_length=1)]


class StrategiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategies: dict[str, Strategy]


def parse_strategies_text(text: str) -> list[Strategy]:
    """Validate a strategies-catalog YAML string, RAISING on any error.

    Same strict, all-or-nothing contract as load_strategies (any error in
    any strategy rejects the whole file) but surfaces the error instead of
    swallowing it — the catalog-editor save path needs the message verbatim.

    Raises:
        yaml.YAMLError: malformed YAML or !!python tags.
        ValueError: empty document.
        pydantic.ValidationError: schema violation.
    """
    raw = yaml.safe_load(text)
    if raw is None:
        raise ValueError("strategies file is empty")

    parsed = StrategiesFile.model_validate(raw)

    result: list[Strategy] = []
    for name, strat in parsed.strategies.items():
        data = strat.model_dump()
        data["name"] = name
        result.append(Strategy.model_validate(data))
    return result


def load_strategies(path: Optional[str] = None) -> list[Strategy]:
    """Load and validate strategies from YAML.

    Returns an empty list on every error path (missing file, empty
    file, malformed YAML, validation failure). Errors are logged at
    WARNING. All-or-nothing: any single validation failure rejects
    the entire file (per D-07).

    Args:
        path: Optional path override. When None, reads STRATEGIES_PATH
            env var (default: "strategies.yaml" relative to CWD).

    Returns:
        List of validated Strategy objects, preserving YAML insertion
        order. Each Strategy has `name` populated from its YAML key.
    """
    if path is None:
        path = os.getenv("STRATEGIES_PATH", "strategies.yaml")

    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        log.warning(
            "strategies.yaml not found at %s — running with no strategies",
            path,
        )
        return []
    except OSError as e:
        log.warning("Failed to read strategies file %s: %s", path, e)
        return []

    try:
        result = parse_strategies_text(text)
    except yaml.YAMLError as e:
        # Covers ConstructorError from !!python tags and parse errors.
        log.warning("Failed to parse strategies file %s: %s", path, e)
        return []
    except ValidationError as e:
        # Subclass of ValueError — must precede the empty-document branch.
        log.warning("strategies file %s failed validation:\n%s", path, e)
        return []
    except ValueError:
        # Empty document (parse_strategies_text raises).
        log.warning("strategies file %s is empty — running with no strategies", path)
        return []

    log.info("Loaded %d strategies from %s", len(result), path)
    return result
