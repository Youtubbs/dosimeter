""" Manual redaction of sensitive fields from normalized exposure data """

# subject to change have to look at packet data
# remove dedect pii permission on IAM

from dosimeter.redaction import PII_FIELD_NAMES, is_redacted_field

SENSITIVE_FIELDS = PII_FIELD_NAMES


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
