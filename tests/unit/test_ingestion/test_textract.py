"""Test suite for textract.py"""

from unittest.mock import patch
from dosimeter.config.settings import get_settings
from dosimeter.ingestion.textract import start_document_analysis


def test_start_document_analysis():

    with patch("dosimeter.ingestion.textract.get_client") as mock_get_client:
        mock_get_client.return_value.start_document_analysis.return_value = {"JobId": "job-123"}

        result = start_document_analysis("exp-0411/exposure-report.pdf")

        assert result == "job-123"

        mock_get_client.return_value.start_document_analysis.assert_called_once_with(
            DocumentLocation={
                "S3Object": {
                    "Bucket": get_settings().packet_bucket,
                    "Name": "exp-0411/exposure-report.pdf",
                }
            },
            FeatureTypes=[
                "FORMS",
                "TABLES",
            ],
        )
