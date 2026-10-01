"""The repository: the one place in the project that talks to the database."""

# re-exported so code outside the repository never imports the database driver
from sqlalchemy.orm import Session

__all__ = ["Session"]
