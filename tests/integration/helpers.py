"""Small stand-ins the database tests share."""

from dosimeter.config.settings import Bounds
from dosimeter.harness.budgets import SessionLedger


class FakeObjectStore:
    """S3 without S3: the pipeline only needs exists and put."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts = 0

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects

    def put(self, bucket: str, key: str, content: bytes) -> None:
        self.objects[(bucket, key)] = content
        self.puts += 1


def ledger_for_tests() -> SessionLedger:
    return SessionLedger(bounds=Bounds())
