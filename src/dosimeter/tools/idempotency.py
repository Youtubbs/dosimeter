"""
Idempotency keys, derived by the harness rather than asked of the model.

Canonicalization is order independent. keys are sorted at every level, so two
calls that differ only in the order of their arguments get the same key.
"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonicalize(arguments: Mapping[str, Any]) -> str:
    """One string for one set of arguments, whatever order they arrived in."""

    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)


def arguments_hash(arguments: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonicalize(arguments).encode("utf-8")).hexdigest()


def idempotency_key(session_id: str, tool_name: str, arguments: Mapping[str, Any]) -> str:
    """The key the harness claims before a tool runs."""

    material = f"{session_id}|{tool_name}|{canonicalize(arguments)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
