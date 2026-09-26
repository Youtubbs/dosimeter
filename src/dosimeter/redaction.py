"""
The one redactor. It works from a list of field names, not from pattern matching,
and everything that leaves the process for a model, a log line or
the index goes through it first.

Removed values are handed back with the field they came from, so the caller can
put them in the detachable identity record and nowhere else.
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


def is_redacted_field(name: str) -> bool:
    """True when a field with this name holds a name or a dose history."""

    normalized = normalize_field_name(name)
    return normalized in PII_FIELD_NAMES or normalized in DOSE_HISTORY_FIELD_NAMES


class RemovedSpan(BaseModel):
    """One value that was taken out, and where it came from."""

    model_config = ConfigDict(frozen=True)

    field_name: str
    value: str
    start: int | None = None
    end: int | None = None


class Redaction(BaseModel):
    """The cleaned value, plus every value that was taken out of it."""

    value: Any
    removed: list[RemovedSpan] = Field(default_factory=list)


def redact_text(text: str) -> Redaction:
    """Blank the value of any labelled line whose label is a redacted field."""

    removed: list[RemovedSpan] = []
    out_lines: list[str] = []
    offset = 0

    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = _LABELLED_LINE.match(stripped)
        if match and is_redacted_field(match.group("label")):
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

    return Redaction(value="".join(out_lines), removed=removed)


def redact_value(value: Any) -> Redaction:
    """Walk a mapping, list or string and take out every redacted field."""

    removed: list[RemovedSpan] = []
    cleaned = _walk(value, removed)
    return Redaction(value=cleaned, removed=removed)


def redact(value: Any) -> Any:
    """The cleaned value only. Log lines, run records and model calls all go through here."""

    return redact_value(value).value


def _walk(value: Any, removed: list[RemovedSpan]) -> Any:
    if isinstance(value, Mapping):
        # a {field, value} pair, the shape the extraction pipeline produces
        if _is_field_record(value):
            return _redact_field_record(value, removed)

        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and is_redacted_field(key):
                removed.append(RemovedSpan(field_name=key, value=_as_text(item)))
                cleaned[key] = REDACTED
            else:
                cleaned[key] = _walk(item, removed)
        return cleaned

    if isinstance(value, str):
        text = redact_text(value)
        removed.extend(text.removed)
        return text.value

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items = [_walk(item, removed) for item in value]
        return tuple(items) if isinstance(value, tuple) else items

    return value


def _is_field_record(value: Mapping[Any, Any]) -> bool:
    return "value" in value and ("field" in value or "field_key" in value or "key" in value)


def _redact_field_record(original: Mapping[Any, Any], removed: list[RemovedSpan]) -> dict:
    label = str(original.get("field") or original.get("field_key") or original.get("key") or "")
    cleaned = dict(original)
    if is_redacted_field(label):
        removed.append(RemovedSpan(field_name=label, value=_as_text(original.get("value"))))
        cleaned["value"] = REDACTED
    return cleaned


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


# subject to change have to look at packet data
def redact_fields(data: dict) -> dict:
    """Remove sensitive identity fields from the main report.

    Sensitive fields are moved into a separate detachable section.
    """

    report_fields = []
    detachable_identity = []

    for field in data.get("fields", []):
        field_name = field.get("field", "").rstrip(":")

        if is_redacted_field(field_name):
            detachable_identity.append(field.copy())
        else:
            report_fields.append(field.copy())

    return {
        "source_artifact": data.get("source_artifact"),
        "fields": report_fields,
        "detachable_identity": detachable_identity,
    }


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
