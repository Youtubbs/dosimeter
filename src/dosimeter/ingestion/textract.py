"""Handles document extraction using Amazon Textract"""

from ..aws.aws import get_client
from ..aws.config import PACKET_BUCKET_NAME

import time


def start_document_analysis(s3_key: str, bucket_name: str = PACKET_BUCKET_NAME) -> str:
    """Start an asynchronous Textract analysis for an S3 document"""

    textract = get_client("textract")

    response = textract.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket_name, "Name": s3_key}},
        FeatureTypes=["FORMS", "TABLES"],
    )

    return response["JobId"]


def wait_for_analysis(job_id: str, poll_interval: int = 2, max_delay=30, max_wait=300) -> str:
    """Wait for a Textract job to finish. Uses exponential backoff while polling Textract"""

    textract = get_client("textract")

    delay = poll_interval
    elapsed = 0

    while elapsed < max_wait:
        response = textract.get_document_analysis(
            JobId=job_id,
        )

        status = response["JobStatus"]

        if status == "SUCCEEDED":
            return status

        if status == "PARTIAL_SUCCESS":
            return status

        if status == "FAILED":
            raise RuntimeError(f"Textract job {job_id} failed.")

        time.sleep(delay)
        elapsed += delay

        delay = min(delay * 2, max_delay)

    raise TimeoutError(f"Textract job {job_id} did not finish within {max_wait} seconds.")


def get_analysis_results(job_id: str) -> list[dict]:
    """Retrieve all Textract analysis results, including paginated results"""

    textract = get_client("textract")

    blocks: list[dict] = []
    next_token: str | None = None

    while True:
        if next_token:
            response = textract.get_document_analysis(JobId=job_id, NextToken=next_token)
        else:
            response = textract.get_document_analysis(JobId=job_id)

        blocks.extend(response.get("Blocks", []))

        next_token = response.get("NextToken")

        if not next_token:
            break

    return blocks


def extract_artifact(s3_key: str, bucket_name: str = PACKET_BUCKET_NAME) -> list[dict]:
    """Run Textract on one S3 artifact and return its extracted blocks."""

    try:
        job_id = start_document_analysis(s3_key=s3_key, bucket_name=bucket_name)

        status = wait_for_analysis(job_id)

        blocks = get_analysis_results(job_id)

        if status == "PARTIAL_SUCCESS":
            print(f"Textract partially processed artifact: {s3_key}")
        return blocks

    # change to custom error later
    except Exception as e:
        print(f"Skipping malformed or unprocessable artifact: {s3_key}: {e}")

        return []
