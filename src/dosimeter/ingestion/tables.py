"""Utilities for validating tables extracted from Amazon Textract"""

from typing import Any


def get_blocks_by_id(blocks: list[dict]) -> dict:
    """Index Textract blocks by their ID"""
    return {block["Id"]: block for block in blocks if "Id" in block}


def get_cell_text(cell: dict, blocks_by_id: dict) -> str:
    """Return the text contained in a Textract CELL block"""
    text_parts: list[str] = []

    for relationship in cell.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue

        for child_id in relationship.get("Ids", []):
            child = blocks_by_id.get(child_id)

            if child and child.get("BlockType") == "WORD":
                text = child.get("Text", "").strip()

                if text:
                    text_parts.append(text)

    return " ".join(text_parts)


def extract_tables(blocks: list[dict]) -> list[list]:
    """
    Extract Textract tables as rows and cells.

    Returns:
        [
            [
                ["Column 1", "Column 2"],
                ["Value 1", "Value 2"],
            ],
            ...
        ]
    """
    blocks_by_id = get_blocks_by_id(blocks)
    tables: list[list[list[str]]] = []

    for table in blocks:
        if table.get("BlockType") != "TABLE":
            continue

        cells: list[dict[str, Any]] = []

        for relationship in table.get("Relationships", []):
            if relationship.get("Type") != "CHILD":
                continue

            for child_id in relationship.get("Ids", []):
                child = blocks_by_id.get(child_id)

                if child and child.get("BlockType") == "CELL":
                    cells.append(child)

        if not cells:
            continue

        max_row = max(cell.get("RowIndex", 0) for cell in cells)
        max_column = max(cell.get("ColumnIndex", 0) for cell in cells)

        rows = [["" for _ in range(max_column)] for _ in range(max_row)]

        for cell in cells:
            row_index = cell.get("RowIndex", 0)
            column_index = cell.get("ColumnIndex", 0)

            if row_index <= 0 or column_index <= 0:
                continue

            rows[row_index - 1][column_index - 1] = get_cell_text(
                cell,
                blocks_by_id,
            )

        tables.append(rows)

    return tables


def reconstruct_wrapped_rows(rows: list[list]) -> list[list]:
    """
    Reconstruct rows where Textract wrapped part of a value
    onto a following physical row.

    Example:

        ["Krypton-85", "1.0", "6,000,"]
        ["", "", "000"]

    becomes:

        ["Krypton-85", "1.0", "6,000,000"]
    """
    reconstructed: list[list[str]] = []

    for row in rows:
        if len(row) < 3:
            reconstructed.append(row)
            continue

        material = row[0].strip()
        release_fraction = row[1].strip()
        quantity = row[2].strip()

        is_continuation = not material and not release_fraction and bool(quantity)

        if is_continuation and reconstructed:
            previous = reconstructed[-1]

            if len(previous) >= 3:
                previous[2] = f"{previous[2]}{quantity}"

            continue

        reconstructed.append(
            [
                material,
                release_fraction,
                quantity,
            ]
        )

    return reconstructed


def validate_schedule_c_rows(rows: list[list[str]]) -> None:
    """
    Validate that Schedule C rows preserve its three columns:

    1. radioactive material
    2. release fraction
    3. quantity
    """
    for row_number, row in enumerate(rows, start=1):
        if len(row) != 3:
            raise ValueError(f"Schedule C row {row_number} has {len(row)} columns; expected 3.")

        material, release_fraction, quantity = row

        if not material:
            raise ValueError(f"Schedule C row {row_number} is missing radioactive material.")

        if not release_fraction:
            raise ValueError(f"Schedule C row {row_number} is missing release fraction.")

        if not quantity:
            raise ValueError(f"Schedule C row {row_number} is missing quantity.")


def verify_schedule_c(blocks: list[dict]) -> list[list]:
    """
    Extract and validate Schedule C table data.

    The caller is responsible for selecting the Schedule C
    table(s) from the CFR-30 Textract output.
    """
    tables = extract_tables(blocks)

    if not tables:
        raise ValueError("No Textract tables were found.")

    for table in tables:
        rows = reconstruct_wrapped_rows(table)

        if not rows:
            continue

        # Schedule C has three columns. Use the first table
        # with a three-column structure as the candidate.
        if all(len(row) == 3 for row in rows):
            validate_schedule_c_rows(rows)
            return rows

    raise ValueError("Could not find a three-column table suitable for Schedule C.")
