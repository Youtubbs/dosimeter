"""Checks on the migration files, so they run without a database."""

from __future__ import annotations

import re

from dosimeter.repository import orm
from dosimeter.repository.migrate import migration_files

SQL = "\n".join(path.read_text(encoding="utf-8") for path in migration_files())

EXPECTED_TABLES = {
    "exposures",
    "artifacts",
    "extracted_fields",
    "officers",
    "grants",
    "worker_dose_histories",
    "historical_exposures",
    "sessions",
    "review_queue",
    "review_decisions",
    "run_records",
    "tool_invocations",
    "rule_invocations",
    "retrievals",
    "model_calls",
    "escalation_triggers",
    "guardrail_events",
    "idempotency_keys",
}

PERSON_NAME_COLUMN = re.compile(
    r"^\s*((?:worker|employee|crew|officer|individual|first|last|full|given|family)_name|name)\s+\w",
    re.MULTILINE,
)


def create_table_blocks() -> dict[str, str]:
    blocks = {}
    for match in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", SQL, re.DOTALL):
        blocks[match.group(1)] = match.group(2)
    return blocks


def test_migrations_are_numbered_and_in_order() -> None:
    names = [path.stem for path in migration_files()]

    assert names == sorted(names)
    assert all(re.match(r"^\d{4}_", name) for name in names)


def test_every_table_the_project_needs_is_created() -> None:
    assert EXPECTED_TABLES <= set(create_table_blocks())


def test_no_column_stores_a_worker_name() -> None:
    columns = {match.group(1) for match in PERSON_NAME_COLUMN.finditer(SQL)}

    assert columns == set(), f"name-bearing columns found: {sorted(columns)}"


def test_the_mapped_tables_match_the_migrations() -> None:
    blocks = create_table_blocks()

    for table in orm.Base.metadata.tables.values():
        if table.name == "schema_migrations":
            continue
        assert table.name in blocks, f"{table.name} is mapped but never created"
        for column in table.columns:
            assert re.search(rf"^\s*{column.name}\s+\w", blocks[table.name], re.MULTILINE), (
                f"{table.name}.{column.name} is mapped but missing from the migration"
            )


def test_the_vector_extension_is_enabled() -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SQL
    assert f"embedding           vector({orm.EMBEDDING_DIMENSIONS})" in SQL
