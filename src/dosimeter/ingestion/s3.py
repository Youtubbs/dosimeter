""" handles s3 bucket ingestion """

from ..aws.aws import get_client
from ..aws.config import PACKET_BUCKET_NAME

import hashlib
from pathlib import Path

ALLOWED_EXTENSIONS = ["pdf", "jpg", "txt"]

def read_file_bytes(file_path: Path) -> bytes:
    """Read a artifact into bytes."""

    return file_path.read_bytes()

def calculate_content_hash(content: bytes) -> str:
    """ Return the hash of an artifact """
    return hashlib.sha256(content).hexdigest()

def find_artifacts(packet_dir: Path) -> list[Path]:
    """ Find all files inside an exposure packet directory """

    if not packet_dir.is_dir():
        raise ValueError(f"Packet directory does not exist: {packet_dir}")

    return [file_path for file_path in packet_dir.rglob("*") if file_path.is_file()]

def upload_artifact(content: bytes, packet_id: str, file_name: str,) -> str:
    """ Upload one artifact to the packets S3 bucket """

    s3_key = f"{packet_id}/{file_name}"

    extension = file_name.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        # need to change this custom exception eventually?
        raise ValueError(f".{extension} is not supported. expected one of the following : {[e for e in ALLOWED_EXTENSIONS]}")

    get_client('s3').put_object(
        Bucket=PACKET_BUCKET_NAME,
        Key=s3_key,
        Body=content,
    )

    return s3_key

def process_artifact(file_path: Path, packet_id: str) -> dict:
    """ Read, hash, and upload one packet artifact """

    content = read_file_bytes(file_path)

    content_hash = calculate_content_hash(content)

    s3_key = upload_artifact(content=content, packet_id=packet_id, file_name=file_path.name)

    return {
        "packet_id": packet_id,
        "file_name": file_path.name,
        "s3_key": s3_key,
        "content_hash": content_hash,
    }

def upload_packet(packet_dir: Path) -> list[dict]:
    """ Process and upload every artifact in an exposure packet """

    packet_id = packet_dir.name

    artifacts = find_artifacts(packet_dir)

    results = []

    for file_path in artifacts:
        result = process_artifact(
            file_path=file_path,
            packet_id=packet_id,
        )
        results.append(result)

    return results
