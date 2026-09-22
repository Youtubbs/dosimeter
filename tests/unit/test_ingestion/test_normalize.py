""" Test suite for normalize.py"""

from dosimeter.ingestion.normalize import normalize

def test_normalize_extracts_form_fields():
    blocks = [
        {
            "Id": "key1",
            "BlockType": "KEY_VALUE_SET",
            "EntityTypes": ["KEY"],
            "Confidence": 99.5,
            "Page": 1,
            "Relationships": [
                {"Type": "CHILD", "Ids": ["word1"]},
                {"Type": "VALUE", "Ids": ["value1"]},
            ],
        },
        {
            "Id": "word1",
            "BlockType": "WORD",
            "Text": "Exposure ID:",
        },
        {
            "Id": "value1",
            "BlockType": "KEY_VALUE_SET",
            "EntityTypes": ["VALUE"],
            "Confidence": 99.0,
            "Page": 1,
            "Relationships": [
                {"Type": "CHILD", "Ids": ["word2"]},
            ],
        },
        {
            "Id": "word2",
            "BlockType": "WORD",
            "Text": "exp-0411",
        },
    ]

    result = normalize(
        blocks=blocks,
        source_artifact="exp-0411/exposure-report.pdf",
    )

    assert result["source_artifact"] == "exp-0411/exposure-report.pdf"
    assert len(result["fields"]) == 1

    field = result["fields"][0]

    assert field["field"] == "Exposure ID:"
    assert field["value"] == "exp-0411"
    assert field["confidence"] == 99.5
    assert field["page"] == 1
