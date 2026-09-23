"""test suite for s3.py"""

from unittest.mock import patch

from dosimeter.ingestion.s3 import upload_packet


def test_upload_packet(tmp_path):
    """Test uploading an entire exposure packet."""

    packet_dir = tmp_path / "exp-0411"
    packet_dir.mkdir()

    exposure_file = packet_dir / "exposure.pdf"
    photo_file = packet_dir / "photo.jpg"

    exposure_file.write_bytes(b"fake exposure contents")
    photo_file.write_bytes(b"fake photo contents")

    with patch("dosimeter.ingestion.s3.get_client") as mock_get_client:
        mock_get_client.return_value.put_object.return_value = {}

        results = upload_packet(packet_dir)

        assert len(results) == 2

        assert results[0]["packet_id"] == "exp-0411"
        assert results[1]["packet_id"] == "exp-0411"

        assert results[0]["file_name"] == "exposure.pdf"
        assert results[1]["file_name"] == "photo.jpg"

        assert results[0]["s3_key"] == "exp-0411/exposure.pdf"
        assert results[1]["s3_key"] == "exp-0411/photo.jpg"

        assert len(results[0]["content_hash"]) == 64
        assert len(results[1]["content_hash"]) == 64

        assert mock_get_client.return_value.put_object.call_count == 2
