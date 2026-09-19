""" Normalize Amazon Textract results into structured exposure data """

def get_text_from_relationships(block: dict, blocks_by_id: dict) -> str:
    """ Get the text connected to a Textract block """

    text_parts = []

    for relationship in block.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue

        for child_id in relationship.get("Ids", []):
            child = blocks_by_id.get(child_id)

            if child and child.get("BlockType") == "WORD":
                text = child.get("Text", "")
                if text:
                    text_parts.append(text)

    return " ".join(text_parts)


def extract_form_fields(blocks: list[dict]) -> list[dict]:
    """ Extract key/value fields from Textract FORMS output """

    blocks_by_id = {
        block["Id"]: block
        for block in blocks
        if "Id" in block
    }

    fields = []

    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET":
            continue

        if "KEY" not in block.get("EntityTypes", []):
            continue

        key_text = get_text_from_relationships(block, blocks_by_id)

        value_block = None

        for relationship in block.get("Relationships", []):
            if relationship.get("Type") != "VALUE":
                continue

            for value_id in relationship.get("Ids", []):
                value_block = blocks_by_id.get(value_id)
                if value_block:
                    break

        if not value_block:
            continue

        value_text = get_text_from_relationships(value_block, blocks_by_id)

        fields.append(
            {
                "field": key_text.strip(),
                "value": value_text.strip(),
                "confidence": block.get("Confidence"),
                "page": block.get("Page"),
            }
        )

    return fields


def normalize(blocks: list[dict], source_artifact: str) -> dict:
    """ Normalize Textract blocks into a structured record """

    fields = extract_form_fields(blocks)

    return {
        "source_artifact": source_artifact,
        "fields": fields,
    }