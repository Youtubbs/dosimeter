""" Test suite for report.py """

from dosimeter.ingestion.report import create_report

def test_report_detects_low_confidence_field():
    data = {
        "source_artifact": "exp-0411/exposure-report.pdf",
        "fields": [
            {
                "field": "Exposure ID",
                "value": "exp-0411",
                "confidence": 0.99,
                "page": 1,
            },
            {
                "field": "Total Effective Dose Equivalent",
                "value": "0.52 rem",
                "confidence": 0.59,
                "page": 1,
            },
        ],
    }

    report = create_report(data)

    assert report["status"] == "processed"
    assert report["fields_extracted"] == 2

    assert len(report["low_confidence_fields"]) == 1

    low_confidence = report["low_confidence_fields"][0]

    assert low_confidence["field"] == "Total Effective Dose Equivalent"
    assert low_confidence["confidence"] == 0.59
    assert low_confidence["page"] == 1

def test_report_accepts_confidence_at_threshold():
    data = {
        "source_artifact": "exp-0411/exposure-report.pdf",
        "fields": [
            {
                "field": "Exposure ID",
                "value": "exp-0411",
                "confidence": 0.70,
                "page": 1,
            },
        ],
    }

    report = create_report(data)

    assert report["low_confidence_fields"] == []
