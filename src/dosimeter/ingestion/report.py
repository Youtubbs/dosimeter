""" Handles ingestion reporting """

# subject to change
CONFIDENCE_THRESHOLD = 0.70

def create_report(data: dict) -> dict:
    """ Create a summary of the ingestion results """

    fields = data.get("fields", [])

    low_confidence_fields = [
        {
            "field": field.get("field"),
            "confidence": field.get("confidence"),
            "page": field.get("page"),
        }
        for field in fields
        if field.get("confidence") is not None
        and field["confidence"] < CONFIDENCE_THRESHOLD
    ]

    return {
        "source_artifact": data.get("source_artifact"),
        "status": "processed",
        "fields_extracted": len(fields),
        "low_confidence_fields": low_confidence_fields,
        "failures": [],     # some form of info should go here
    }
