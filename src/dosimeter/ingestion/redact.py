""" Manual redaction of sensitive fields from normalized exposure data """

# subject to change have to look at packet data
# remove dedect pii permission on IAM

SENSITIVE_FIELDS = {
    "worker name",
    "employee name",
    "name",
    "address",
    "phone",
    "phone number",
    "email",
    "email address",
}


def redact_fields(data: dict) -> dict:
    """Remove sensitive identity fields from the main report.

    Sensitive fields are moved into a separate detachable section.
    """

    report_fields = []
    detachable_identity = []

    for field in data.get("fields", []):
        field_name = field.get("field", "").strip().lower().rstrip(":")

        if field_name in SENSITIVE_FIELDS:
            detachable_identity.append(field.copy())
        else:
            report_fields.append(field.copy())

    return {
        "source_artifact": data.get("source_artifact"),
        "fields": report_fields,
        "detachable_identity": detachable_identity,
    }