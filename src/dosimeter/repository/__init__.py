"""repository package."""

from sqlalchemy.orm import Session  # noqa: E402 - re-exported so callers never import the driver

__all__ = ["Session"]
