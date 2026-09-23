""" Ingest the regulatory corpus through Amazon Textract """

import json
from pathlib import Path

from ..aws.aws import get_client
from ..aws.config import CORPUS_BUCKET_NAME
from .textract import extract_artifact
from .s3 import calculate_content_hash, read_file_bytes

CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus" / "pdf"
CACHE_PREFIX = "textract-cache"

def get_cache_key(file_name: str, content_hash: str) -> str:
    """ Build the S3 key used to cache raw Textract results """

    return f"{CACHE_PREFIX}/{content_hash}/{file_name}.json"

def get_cached_results(cache_key: str) -> list[dict] | None:
    """ Return cached Textract blocks if they exist """

    s3 = get_client("s3")

    try:
        response = s3.get_object(
            Bucket=CORPUS_BUCKET_NAME,
            Key=cache_key,
        )
    except s3.exceptions.NoSuchKey:
        return None
    except Exception as exc:
        error_code = exc.response.get("Error", {}).get("Code")

        if error_code in {"NoSuchKey", "404"}:
            return None

        raise

    data = response["Body"].read()
    return json.loads(data)


def save_cached_results(cache_key: str, blocks: list[dict]) -> None:
    """ Save raw Textract blocks to the corpus cache """

    s3 = get_client("s3")

    s3.put_object(
        Bucket=CORPUS_BUCKET_NAME,
        Key=cache_key,
        Body=json.dumps(blocks).encode("utf-8"),
        ContentType="application/json",
    )


def upload_corpus_document(file_path: Path) -> str:
    """ Upload a corpus PDF to the corpus S3 bucket """

    s3 = get_client("s3")

    key = f"pdf/{file_path.name}"

    s3.upload_file(
        str(file_path),
        CORPUS_BUCKET_NAME,
        key,
    )

    return key


def process_corpus_document(file_path: Path) -> dict:
    """
    Process one corpus PDF.

    Uses the document hash to make Textract processing idempotent.
    If raw Textract results already exist in the cache, they are reused.
    """

    content_hash = calculate_content_hash(read_file_bytes(file_path))

    cache_key = get_cache_key(
        file_name=file_path.stem,
        content_hash=content_hash,
    )

    cached_blocks = get_cached_results(cache_key)

    if cached_blocks is not None:
        return {
            "document": file_path.name,
            "content_hash": content_hash,
            "cache_key": cache_key,
            "blocks": cached_blocks,
            "cached": True,
        }

    s3_key = upload_corpus_document(file_path)

    blocks = extract_artifact(s3_key, CORPUS_BUCKET_NAME)

    if not blocks:
        raise RuntimeError(
            f"Textract returned no blocks for {file_path.name}"
        )

    save_cached_results(
        cache_key=cache_key,
        blocks=blocks,
    )

    return {
        "document": file_path.name,
        "content_hash": content_hash,
        "cache_key": cache_key,
        "blocks": blocks,
        "cached": False,
    }


def process_corpus(corpus_dir: Path = CORPUS_DIR) -> list[dict]:
    """
    Process every PDF in the regulatory corpus.

    A failure in one document does not stop the remaining documents.
    """

    if not corpus_dir.is_dir():
        raise ValueError(f"Corpus directory does not exist: {corpus_dir}")

    pdf_files = sorted(corpus_dir.glob("*.pdf"))

    if not pdf_files:
        raise ValueError(f"No PDF files found in {corpus_dir}")

    results: list[dict] = []

    for file_path in pdf_files:
        try:
            result = process_corpus_document(file_path)
            results.append(result)

        except Exception as exc:
            print(
                f"Skipping corpus document {file_path.name}: {exc}"
            )

            results.append(
                {
                    "document": file_path.name,
                    "error": str(exc),
                    "blocks": [],
                }
            )

    return results
