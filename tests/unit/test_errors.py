"""Each kind of failure has its own error class, so you can catch just one."""

import pytest

from dosimeter.errors import (
    BudgetError,
    ConfigurationError,
    DosimeterError,
    EntitlementError,
    ExternalServiceError,
    ExtractionError,
    GateError,
    RetrievalError,
    RulesError,
)

SUBCLASSES = [
    ConfigurationError,
    ExtractionError,
    RetrievalError,
    RulesError,
    GateError,
    EntitlementError,
    BudgetError,
    ExternalServiceError,
]


@pytest.mark.parametrize("error_type", SUBCLASSES)
def test_every_error_is_a_dosimeter_error(error_type: type[DosimeterError]) -> None:
    assert issubclass(error_type, DosimeterError)


@pytest.mark.parametrize("error_type", SUBCLASSES)
def test_catching_one_type_does_not_catch_another(error_type: type[DosimeterError]) -> None:
    others = [item for item in SUBCLASSES if item is not error_type]

    for other in others:
        with pytest.raises(other):
            raise other("boom")

    with pytest.raises(error_type):
        raise error_type("boom")


def test_a_retrieval_failure_is_not_a_budget_failure() -> None:
    with pytest.raises(RetrievalError):
        try:
            raise RetrievalError("no usable chunks")
        except BudgetError:  # proves the types do not overlap
            pytest.fail("RetrievalError was caught as a BudgetError")


def test_context_is_carried_and_rendered() -> None:
    error = BudgetError("token ceiling reached", agent="coordinator", limit=4096)

    assert error.context == {"agent": "coordinator", "limit": 4096}
    assert "agent='coordinator'" in str(error)
    assert error.message == "token ceiling reached"


def test_error_without_context_renders_its_message_only() -> None:
    assert str(GateError("output blocked")) == "output blocked"
