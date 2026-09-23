from dosimeter.ingestion.sectioning import (
    build_sections,
    extract_section_path,
    get_text_lines,
    is_section_heading,
)


def test_get_text_lines_extracts_line_blocks():
    blocks = [
        {
            "BlockType": "LINE",
            "Page": 2,
            "Text": "Hello world",
        },
        {
            "BlockType": "WORD",
            "Page": 2,
            "Text": "ignored",
        },
    ]

    assert get_text_lines(blocks) == [
        (2, "Hello world"),
    ]


def test_cfr_heading_is_detected():
    assert is_section_heading(
        "§ 20.1201 Occupational dose limits for adults."
    )


def test_non_heading_is_not_detected():
    assert not is_section_heading(
        "(a) The licensee shall control..."
    )


def test_extract_section_path():
    assert (
        extract_section_path(
            "§ 20.1201 Occupational dose limits for adults."
        )
        == "§ 20.1201"
    )


def test_build_sections():
    blocks = [
        {
            "BlockType": "LINE",
            "Page": 1,
            "Text": "§ 20.1201 Occupational dose limits for adults.",
        },
        {
            "BlockType": "LINE",
            "Page": 1,
            "Text": "(a) The licensee shall control exposure.",
        },
        {
            "BlockType": "LINE",
            "Page": 2,
            "Text": "§ 20.1202 Dose limits for individual members.",
        },
        {
            "BlockType": "LINE",
            "Page": 2,
            "Text": "(a) Additional requirements apply.",
        },
    ]

    sections = build_sections(
        blocks,
        doc_id="CFR-20-LIMITS",
        title="Occupational Dose Limits",
        doc_type="cfr",
        status="in_force",
    )

    assert len(sections) == 2

    assert sections[0].section_path == "§ 20.1201"
    assert sections[0].page == 1
    assert "(a) The licensee shall control exposure." in sections[0].text

    assert sections[1].section_path == "§ 20.1202"
    assert sections[1].page == 2
    assert "(a) Additional requirements apply." in sections[1].text


def test_build_sections_preserves_metadata():
    blocks = [
        {
            "BlockType": "LINE",
            "Page": 3,
            "Text": "§ 34.20 Requirements.",
        }
    ]

    sections = build_sections(
        blocks,
        doc_id="CFR-34",
        title="Radiography",
        doc_type="cfr",
        status="in_force",
    )

    section = sections[0]

    assert section.doc_id == "CFR-34"
    assert section.title == "Radiography"
    assert section.doc_type == "cfr"
    assert section.status == "in_force"