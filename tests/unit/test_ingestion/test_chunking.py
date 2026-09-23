from dosimeter.ingestion.chunking import (
    CorpusSection,
    create_chunk_id,
    split_by_size,
    chunk_section,
)


def test_small_section_stays_as_one_chunk():
    section = CorpusSection(
        doc_id="CFR-20-LIMITS",
        title="Dose Limits",
        doc_type="regulation",
        status="in_force",
        section_path="20.1201",
        page=3,
        text="This is a short regulatory section.",
    )

    chunks = chunk_section(section, chunk_size=1000)

    assert len(chunks) == 1
    assert chunks[0].text == section.text
    assert chunks[0].doc_id == "CFR-20-LIMITS"
    assert chunks[0].section_path == "20.1201"
    assert chunks[0].status == "in_force"


def test_large_section_is_split():
    text = "A" * 250

    chunks = split_by_size(
        text,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert len(chunks) == 3
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_chunk_records_size_and_overlap():
    section = CorpusSection(
        doc_id="CFR-20-LIMITS",
        title="Dose Limits",
        doc_type="regulation",
        status="in_force",
        section_path="20.1201",
        page=3,
        text="A" * 250,
    )

    chunks = chunk_section(
        section,
        chunk_size=100,
        chunk_overlap=20,
    )

    assert chunks[0].size == 100
    assert chunks[0].overlap == 0
    assert chunks[1].overlap == 20


def test_chunk_id_is_deterministic():
    first = create_chunk_id(
        "CFR-20-LIMITS",
        "20.1201",
        3,
        0,
        "test text",
    )

    second = create_chunk_id(
        "CFR-20-LIMITS",
        "20.1201",
        3,
        0,
        "test text",
    )

    assert first == second


def test_proposed_status_is_preserved():
    section = CorpusSection(
        doc_id="FR-DOSE",
        title="Proposed Framework",
        doc_type="federal_register",
        status="proposed",
        section_path="proposal",
        page=2,
        text="Proposed regulatory text.",
    )

    chunks = chunk_section(section)

    assert chunks[0].status == "proposed"