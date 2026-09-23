import pytest

from dosimeter.ingestion.tables import (
    extract_tables,
    get_blocks_by_id,
    get_cell_text,
    reconstruct_wrapped_rows,
    validate_schedule_c_rows,
)


def test_get_blocks_by_id():
    blocks = [
        {"Id": "1", "BlockType": "WORD", "Text": "Actinium"},
        {"Id": "2", "BlockType": "CELL"},
    ]

    result = get_blocks_by_id(blocks)

    assert result["1"]["Text"] == "Actinium"
    assert result["2"]["BlockType"] == "CELL"


def test_get_cell_text():
    blocks = [
        {
            "Id": "cell-1",
            "BlockType": "CELL",
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": ["word-1", "word-2"],
                }
            ],
        },
        {
            "Id": "word-1",
            "BlockType": "WORD",
            "Text": "Actinium-228",
        },
        {
            "Id": "word-2",
            "BlockType": "WORD",
            "Text": "4,000",
        },
    ]

    blocks_by_id = get_blocks_by_id(blocks)

    result = get_cell_text(
        blocks_by_id["cell-1"],
        blocks_by_id,
    )

    assert result == "Actinium-228 4,000"


def test_extract_tables():
    blocks = [
        {
            "Id": "table-1",
            "BlockType": "TABLE",
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": ["cell-1", "cell-2"],
                }
            ],
        },
        {
            "Id": "cell-1",
            "BlockType": "CELL",
            "RowIndex": 1,
            "ColumnIndex": 1,
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": ["word-1"],
                }
            ],
        },
        {
            "Id": "cell-2",
            "BlockType": "CELL",
            "RowIndex": 1,
            "ColumnIndex": 2,
            "Relationships": [
                {
                    "Type": "CHILD",
                    "Ids": ["word-2"],
                }
            ],
        },
        {
            "Id": "word-1",
            "BlockType": "WORD",
            "Text": "Material",
        },
        {
            "Id": "word-2",
            "BlockType": "WORD",
            "Text": "Quantity",
        },
    ]

    result = extract_tables(blocks)

    assert result == [
        [
            ["Material", "Quantity"],
        ]
    ]


def test_reconstruct_wrapped_quantity():
    rows = [
        ["Krypton-85", "1.0", "6,000,"],
        ["", "", "000"],
    ]

    result = reconstruct_wrapped_rows(rows)

    assert result == [
        ["Krypton-85", "1.0", "6,000,000"],
    ]


def test_reconstruct_wrapped_californium_quantity():
    rows = [
        ["Californium-252", ".001", "9 (20"],
        ["", "", "mg)"],
    ]

    result = reconstruct_wrapped_rows(rows)

    assert result == [
        ["Californium-252", ".001", "9 (20mg)"],
    ]


def test_reconstruct_multiple_wrapped_rows():
    rows = [
        ["Chromium-51", ".01", "300,00"],
        ["", "", "0"],
        ["Cobalt-60", ".001", "5,000"],
        ["Copper-64", ".01", "200,00"],
        ["", "", "0"],
    ]

    result = reconstruct_wrapped_rows(rows)

    assert result == [
        ["Chromium-51", ".01", "300,000"],
        ["Cobalt-60", ".001", "5,000"],
        ["Copper-64", ".01", "200,000"],
    ]


def test_validate_schedule_c_rows():
    rows = [
        ["Actinium-228", "0.001", "4,000"],
        ["Americium-241", ".001", "2"],
        ["Barium-133", ".01", "10,000"],
    ]

    validate_schedule_c_rows(rows)


def test_validate_schedule_c_keeps_release_fraction_separate():
    rows = [
        ["Actinium-228", "0.001", "4,000"],
    ]

    validate_schedule_c_rows(rows)

    material, release_fraction, quantity = rows[0]

    assert material == "Actinium-228"
    assert release_fraction == "0.001"
    assert quantity == "4,000"
    assert release_fraction != quantity


@pytest.mark.parametrize(
    "row",
    [
        ["Actinium-228", "0.001"],
        ["Actinium-228", "0.001", "4,000", "extra"],
        ["", "0.001", "4,000"],
        ["Actinium-228", "", "4,000"],
        ["Actinium-228", "0.001", ""],
    ],
)
def test_validate_schedule_c_rejects_invalid_rows(
    row: list[str],
):
    with pytest.raises(ValueError):
        validate_schedule_c_rows([row])
