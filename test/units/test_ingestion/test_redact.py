""" Test suite for redact.py """

from dosimeter.ingestion.redact import redact_fields


def test_redact_moves_sensitive_fields_to_detachable_identity():
    data = {
        "source_artifact": "exp-0411/exposure-report.pdf",
        "fields": [
            {
                "field": "Worker Name",
                "value": "John Smith",
                "confidence": 99.0,
                "page": 1,
            },
            {
                "field": "Worker ID",
                "value": "W-1042",
                "confidence": 99.0,
                "page": 1,
            },
            {
                "field": "District",
                "value": "District 2",
                "confidence": 99.0,
                "page": 1,
            },
        ],
    }

    result = redact_fields(data)

    assert len(result["fields"]) == 2
    assert len(result["detachable_identity"]) == 1

    assert result["detachable_identity"][0]["field"] == "Worker Name"

    remaining_fields = {
        field["field"]
        for field in result["fields"]
    }

    assert "Worker ID" in remaining_fields
    assert "District" in remaining_fields
    assert "Worker Name" not in remaining_fields