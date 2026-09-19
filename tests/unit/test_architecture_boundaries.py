"""
This test reads our own source files and fails if code does something in the
wrong place. The rules:

  - only files under aws/ may import boto3
  - only files under retrieval/ may search the Knowledge Base
  - only files under repository/ may talk to the database
  - nobody builds a SQL string with an f-string or a %. use query parameters

It reads the files as code rather than searching the text, so a word inside a
comment or a docstring does not set it off. The sample files in
tests/fixtures/boundaries/ break the rules on purpose, which is how we know the
test would actually catch it.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "dosimeter"
BAD_SAMPLES = Path(__file__).resolve().parents[1] / "fixtures" / "boundaries"

AWS_CLIENT_MODULES = ("dosimeter/aws/",)
RETRIEVAL_MODULES = ("dosimeter/retrieval/",)
REPOSITORY_MODULES = ("dosimeter/repository/",)

AWS_SDK_ROOTS = frozenset({"boto3", "botocore"})
DB_DRIVER_ROOTS = frozenset({"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "flask_sqlalchemy"})
KB_CALL_NAMES = frozenset({"retrieve", "retrieve_and_generate"})
KB_SERVICE_NAMES = frozenset({"bedrock-agent-runtime", "bedrock-agent"})
SQL_CALL_NAMES = frozenset({"execute", "executemany", "executescript"})
SQL_KEYWORDS = (
    "select ",
    "insert into",
    "update ",
    "delete from",
    "create table",
    "alter table",
    "drop table",
    "with ",
)


@dataclass(frozen=True)
class Violation:
    """One broken rule, and where it is."""

    module: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line} [{self.rule}] {self.detail}"


def _is_allowed(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module.startswith(prefix) for prefix in prefixes)


def _root_package(name: str) -> str:
    return name.split(".", 1)[0]


def _looks_like_sql(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in SQL_KEYWORDS)


def _joined_string_text(node: ast.JoinedStr) -> str:
    return "".join(part.value for part in node.values if isinstance(part, ast.Constant))


def scan_source(source: str, module: str) -> list[Violation]:
    """Check one file and return everything it got wrong."""

    tree = ast.parse(source, filename=module)
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                violations.extend(_check_import(_root_package(alias.name), module, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            violations.extend(_check_import(_root_package(node.module), module, node.lineno))
        elif isinstance(node, ast.Call):
            violations.extend(_check_call(node, module))
        elif isinstance(node, ast.JoinedStr):
            if _looks_like_sql(_joined_string_text(node)) and any(
                isinstance(part, ast.FormattedValue) for part in node.values
            ):
                violations.append(
                    Violation(
                        module,
                        node.lineno,
                        "sql-string-building",
                        "SQL built with an f-string; use query parameters instead",
                    )
                )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = node.left
            if isinstance(left, ast.Constant) and isinstance(left.value, str):
                if _looks_like_sql(left.value):
                    violations.append(
                        Violation(
                            module,
                            node.lineno,
                            "sql-string-building",
                            "SQL built with percent formatting; use query parameters instead",
                        )
                    )

    return violations


def _check_import(root: str, module: str, line: int) -> list[Violation]:
    if root in AWS_SDK_ROOTS and not _is_allowed(module, AWS_CLIENT_MODULES):
        return [
            Violation(
                module,
                line,
                "aws-client-boundary",
                f"imports {root}; only the AWS client module builds AWS clients",
            )
        ]
    if root in DB_DRIVER_ROOTS and not _is_allowed(module, REPOSITORY_MODULES):
        return [
            Violation(
                module,
                line,
                "repository-boundary",
                f"imports {root}; only the repository module talks to the database",
            )
        ]
    return []


def _check_call(node: ast.Call, module: str) -> list[Violation]:
    violations: list[Violation] = []
    name = node.func.attr if isinstance(node.func, ast.Attribute) else None

    if name in KB_CALL_NAMES and not _is_allowed(module, RETRIEVAL_MODULES):
        violations.append(
            Violation(
                module,
                node.lineno,
                "retrieval-boundary",
                f"calls {name}(); only the retrieval module queries the Knowledge Base",
            )
        )

    if name in SQL_CALL_NAMES and not _is_allowed(module, REPOSITORY_MODULES):
        violations.append(
            Violation(
                module,
                node.lineno,
                "repository-boundary",
                f"calls {name}(); every query goes through the repository module",
            )
        )

    for argument in node.args:
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            if argument.value in KB_SERVICE_NAMES and not _is_allowed(module, AWS_CLIENT_MODULES):
                violations.append(
                    Violation(
                        module,
                        node.lineno,
                        "aws-client-boundary",
                        f"builds a {argument.value} client; only the AWS client module does",
                    )
                )

    return violations


def scan_package() -> list[Violation]:
    """Check every file in the package."""

    violations: list[Violation] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module = path.relative_to(PACKAGE_ROOT.parent).as_posix()
        violations.extend(scan_source(path.read_text(encoding="utf-8"), module))
    return violations


def _scan_sample(filename: str, module: str) -> list[Violation]:
    source = (BAD_SAMPLES / filename).read_text(encoding="utf-8")
    return scan_source(source, module)


def test_package_has_no_boundary_violations() -> None:
    violations = scan_package()
    assert violations == [], "\n".join(str(item) for item in violations)


def test_boto3_import_outside_the_aws_module_fails() -> None:
    violations = _scan_sample("bad_boto3_import.py.txt", "dosimeter/tools/bad_tool.py")

    assert [item.rule for item in violations] == ["aws-client-boundary"]


def test_boto3_import_inside_the_aws_module_is_allowed() -> None:
    violations = _scan_sample("bad_boto3_import.py.txt", "dosimeter/aws/client.py")

    assert violations == []


def test_knowledge_base_call_outside_retrieval_fails() -> None:
    violations = _scan_sample("bad_knowledge_base_call.py.txt", "dosimeter/tools/bad_tool.py")

    assert {item.rule for item in violations} == {"retrieval-boundary"}


def test_knowledge_base_call_inside_retrieval_is_allowed() -> None:
    violations = _scan_sample("bad_knowledge_base_call.py.txt", "dosimeter/retrieval/search.py")

    assert violations == []


def test_sql_execution_outside_the_repository_fails() -> None:
    violations = _scan_sample("bad_sql_execution.py.txt", "dosimeter/tools/bad_tool.py")

    rules = {item.rule for item in violations}
    assert "repository-boundary" in rules


def test_fstring_sql_fails_even_inside_the_repository() -> None:
    violations = _scan_sample("bad_fstring_sql.py.txt", "dosimeter/repository/queries.py")

    assert [item.rule for item in violations] == ["sql-string-building"]


def test_percent_formatted_sql_fails_even_inside_the_repository() -> None:
    violations = _scan_sample("bad_percent_sql.py.txt", "dosimeter/repository/queries.py")

    assert [item.rule for item in violations] == ["sql-string-building"]


def test_parameterized_repository_query_passes() -> None:
    violations = _scan_sample("good_repository_query.py.txt", "dosimeter/repository/queries.py")

    assert violations == []
