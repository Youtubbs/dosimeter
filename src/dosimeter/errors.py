""" All the errors this project raises, so each kind of failure can be caught on its own """

from typing import Any


class DosimeterError(Exception):
    """ Parent of every error we raise.

        Extra keyword arguments are kept as context and printed with the message,
        so a log line says which field or file the error was about.
    """

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:
        if not self.context:
            return self.message
        details = ", ".join(f"{key}={value!r}" for key, value in sorted(self.context.items()))
        return f"{self.message} ({details})"


class ConfigurationError(DosimeterError):
    """A setting is missing, wrong, or conflicts with another one."""


# the requirements ask that extraction, retrieval, rules and gate failures
# can be told apart by type
class ExtractionError(DosimeterError):
    """We could not read a packet or a corpus document."""


class RetrievalError(DosimeterError):
    """The search came back empty or failed."""


class RulesError(DosimeterError):
    """The rules engine could not reach an answer."""


class GateError(DosimeterError):
    """A guardrail blocked the request or the answer."""


class EntitlementError(DosimeterError):
    """This caller is not allowed to see that, or do that."""


class BudgetError(DosimeterError):
    """A limit ran out: tokens, tool calls, depth or time."""


class ExternalServiceError(DosimeterError):
    """An outside service failed and the retries are used up."""
