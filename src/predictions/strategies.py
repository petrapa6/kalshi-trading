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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)


class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sport: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `name` is injected by load_strategies() from the YAML dict key.
    # It is not present in the YAML body and the strict-extras config does
    # not complain because the loader post-processes parsed strategies.
    name: str = ""
    description: Optional[str] = None
    triggers: Annotated[list[Trigger], Field(min_length=1)]


class StrategiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategies: dict[str, Strategy]


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
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        log.warning(
            "strategies.yaml not found at %s — running with no strategies",
            path,
        )
        return []
    except OSError as e:
        log.warning("Failed to read strategies file %s: %s", path, e)
        return []
    except yaml.YAMLError as e:
        # Covers ConstructorError from !!python tags and parse errors.
        log.warning("Failed to parse strategies file %s: %s", path, e)
        return []

    if raw is None:
        log.warning("strategies file %s is empty — running with no strategies", path)
        return []

    try:
        parsed = StrategiesFile.model_validate(raw)
    except ValidationError as e:
        log.warning("strategies file %s failed validation:\n%s", path, e)
        return []

    # Inject `name` from the dict key. Insertion order is preserved by
    # dict iteration in Python 3.7+.
    result: list[Strategy] = []
    for name, strat in parsed.strategies.items():
        data = strat.model_dump()
        data["name"] = name
        result.append(Strategy.model_validate(data))

    log.info("Loaded %d strategies from %s", len(result), path)
    return result
