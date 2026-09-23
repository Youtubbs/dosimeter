"""
The one redactor. It works from a list of field names, not from pattern matching, 
and everything that leaves the process for a model, a log line or
the index goes through it first.

Removed values are handed back with the field they came from, so the caller can
put them in the detachable identity record and nowhere else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REDACTED = "[redacted]"

PII_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "worker name",
        "workers name",
        "employee name",
        "crew name",
        "crew names",
        "crew chief",
        "crew member",
        "crew members",
        "supervisor",
        "supervisor name",
        "individual",
        "individual name",
        "name",
        "full name",
        "first name",
        "last name",
        "signature",
        "signed by",
        "ssn",
        "social security number",
        "dob",
        "date of birth",
        "address",
        "home address",
        "phone",
        "phone number",
        "email",
        "email address",
    }
)

# Dose histories are as sensitive as a name and never reach a log line either.
DOSE_HISTORY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "dose history",
        "dose histories",
        "lifetime dose",
        "prior lifetime dose",
        "prior dose",
        "worker dose history",
        "worker dose histories",
        "planned special exposure lifetime",
        "planned_special_exposure_lifetime",
    }
)

_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_LABELLED_LINE = re.compile(r"^(?P<label>[A-Za-z][A-Za-z /_-]{0,40}):[ \t]*(?P<value>.+)$")


def normalize_field_name(name: str) -> str:
    """Field names compare on letters and digits only."""

    return _PUNCTUATION.sub(" ", name.strip().lower()).strip()


def is_redacted_field(name: str, extra_fields: Iterable[str] = ()) -> bool:
    normalized = normalize_field_name(name)
    if normalized in PII_FIELD_NAMES or normalized in DOSE_HISTORY_FIELD_NAMES:
        return True
    return normalized in {normalize_field_name(item) for item in extra_fields}


@dataclass(frozen=True)
class RemovedSpan:
    """One value that was taken out, and where it came from."""

    field_name: str
    value: str
    start: int | None = None
    end: int | None = None


@dataclass
class Redaction:
    value: Any
    removed: list[RemovedSpan] = field(default_factory=list)


def redact_text(text: str, extra_fields: Iterable[str] = ()) -> Redaction:
    """Blank the value of any labelled line whose label is a redacted field."""

    removed: list[RemovedSpan] = []
    out_lines: list[str] = []
    offset = 0

    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = _LABELLED_LINE.match(stripped)
        if match and is_redacted_field(match.group("label"), extra_fields):
            value = match.group("value").strip()
            start = offset + match.start("value")
            removed.append(
                RemovedSpan(
                    field_name=match.group("label").strip(),
                    value=value,
                    start=start,
                    end=start + len(value),
                )
            )
            ending = line[len(stripped) :]
            out_lines.append(f"{match.group('label')}: {REDACTED}{ending}")
        else:
            out_lines.append(line)
        offset += len(line)

    return Redaction("".join(out_lines), removed)


def redact_value(value: Any, extra_fields: Iterable[str] = ()) -> Redaction:
    """Walk a mapping, sequence or string and take out every redacted field."""

    removed: list[RemovedSpan] = []

    if isinstance(value, Mapping):
        if _is_field_record(value):
            return _redact_field_record(value, extra_fields)

        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and is_redacted_field(key, extra_fields):
                removed.append(RemovedSpan(field_name=key, value=_as_text(item)))
                cleaned[key] = REDACTED
                continue
            nested = redact_value(item, extra_fields)
            cleaned[key] = nested.value
            removed.extend(nested.removed)
        return Redaction(cleaned, removed)

    if isinstance(value, str):
        text = redact_text(value, extra_fields)
        return Redaction(text.value, text.removed)

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items = []
        for item in value:
            nested = redact_value(item, extra_fields)
            items.append(nested.value)
            removed.extend(nested.removed)
        return Redaction(type(value)(items) if isinstance(value, tuple) else items, removed)

    return Redaction(value, removed)


def _is_field_record(value: Mapping[Any, Any]) -> bool:
    """A {field, value} pair, the shape the extraction pipeline produces."""

    return "value" in value and ("field" in value or "field_key" in value or "key" in value)


def _redact_field_record(original: Mapping[Any, Any], extra_fields: Iterable[str]) -> Redaction:
    label = str(original.get("field") or original.get("field_key") or original.get("key") or "")
    if not is_redacted_field(label, extra_fields):
        return Redaction(dict(original), [])

    cleaned = dict(original)
    cleaned["value"] = REDACTED
    return Redaction(
        cleaned,
        [RemovedSpan(field_name=label, value=_as_text(original.get("value")))],
    )


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def redact_for_model(payload: Any) -> Any:
    """Everything sent to a model goes through here first."""

    return redact_value(payload).value


def redact_for_index(payload: Any) -> Any:
    """Everything written to the index goes through here first."""

    return redact_value(payload).value


def redact_for_log(payload: Any) -> Any:
    """Everything written to a log line goes through here first."""

    return redact_value(payload).value


class IdentityVault:
    """
    The detachable record. Names live here and are never joined into a dossier,
    a run record or the index. See 20.2202(c) on keeping names separable.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, exposure_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", exposure_id)
        return self.root / f"{safe}.json"

    def store(self, exposure_id: str, removed: Sequence[RemovedSpan]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(exposure_id)
        payload = {
            "exposure_id": exposure_id,
            "identities": [
                {"field_name": span.field_name, "value": span.value} for span in removed
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load(self, exposure_id: str) -> list[dict[str, str]]:
        path = self._path(exposure_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["identities"]
