""" Handles document extraction using Amazon Textract """

from ..aws.aws import get_client
from ..aws.config import PACKET_BUCKET_NAME

import time

textract = get_client("textract")

def start_document_analysis(s3_key: str) -> str:
    """ Start an asynchronous Textract analysis for an S3 document """

    response = textract.start_document_analysis(
        DocumentLocation={
            "S3Object": {
                "Bucket": PACKET_BUCKET_NAME,
                "Name": s3_key
            }
        },
        FeatureTypes=[
            "FORMS",
            "TABLES"
        ],
    )

    return response["JobId"]

def wait_for_analysis(job_id: str, poll_interval: int = 2) -> None:
    """ Wait until the Textract analysis finishes """

    while True:
        response = textract.get_document_analysis(JobId=job_id,)

        status = response["JobStatus"]

        if status == "SUCCEEDED":
            return

        if status in {"FAILED", "PARTIAL_SUCCESS"}:
            raise RuntimeError(
                f"Textract job {job_id} finished with status: {status}"
            )

        time.sleep(poll_interval)

def get_analysis_results(job_id: str) -> list[dict]:
    """ Retrieve all Textract analysis results, including paginated results """

    blocks: list[dict] = []
    next_token: str | None = None

    while True:
        if next_token:
            response = textract.get_document_analysis(
                JobId=job_id,
                NextToken=next_token
            )
        else:
            response = textract.get_document_analysis(JobId=job_id)

        blocks.extend(response.get("Blocks", []))

        next_token = response.get("NextToken")

        if not next_token:
            break

    return blocks

def extract_artifact(s3_key: str) -> list[dict]:
    """Run Textract on one S3 artifact and return its extracted blocks."""

    try:
        job_id = start_document_analysis(s3_key=s3_key)

        wait_for_analysis(job_id)

        return get_analysis_results(job_id)

    except Exception as e:
        print(f"Skipping malformed or unprocessable artifact: " f"{s3_key}: {e}")

        return []


if __name__ == "__main__":
    results = extract_artifact("exp-0411/exposure-report.pdf")

    print(f"Extracted {len(results)} blocks")

    for block in results[:10]:
        print(block)