"""
Idempotency keys, derived by the harness rather than asked of the model.

Canonicalization is order independent. keys are sorted, numbers are normalized
to a single spelling, and units are normalized to one name each, so two calls
that mean the same thing produce the same key.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

UNIT_ALIASES: dict[str, str] = {
    "rem": "rem",
    "rems": "rem",
    "millirem": "mrem",
    "millirems": "mrem",
    "mrem": "mrem",
    "rad": "rad",
    "rads": "rad",
    "millirad": "mrad",
    "mrad": "mrad",
    "sievert": "sv",
    "sieverts": "sv",
    "sv": "sv",
    "gray": "gy",
    "grays": "gy",
    "gy": "gy",
}

UNIT_KEYS = frozenset({"unit", "units", "dose_unit", "quantity_unit"})


def normalize_number(value: float | int) -> float | int:
    """Numbers compare by value, so 5, 5.0 and 5.00 are one thing."""

    if isinstance(value, bool):
        return value
    number = float(value)
    return int(number) if number.is_integer() else round(number, 6)


def normalize_unit(value: str) -> str:
    return UNIT_ALIASES.get(value.strip().lower(), value.strip().lower())


def canonical_value(key: str | None, value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(item): canonical_value(str(item), value[item]) for item in sorted(value)}

    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [canonical_value(None, item) for item in value]

    if isinstance(value, bool):
        return value

    if isinstance(value, int | float):
        return normalize_number(value)

    if isinstance(value, str):
        if key is not None and key.lower() in UNIT_KEYS:
            return normalize_unit(value)
        return value.strip()

    return value


def canonicalize(arguments: Mapping[str, Any]) -> str:
    """One string for one set of arguments, whatever order they arrived in."""

    return json.dumps(canonical_value(None, arguments), sort_keys=True, separators=(",", ":"))


def arguments_hash(arguments: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonicalize(arguments).encode("utf-8")).hexdigest()


def idempotency_key(session_id: str, tool_name: str, arguments: Mapping[str, Any]) -> str:
    """The key the harness claims before a tool runs."""

    material = f"{session_id}|{tool_name}|{canonicalize(arguments)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
