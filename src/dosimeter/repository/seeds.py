"""
Seed officers, district grants, worker dose histories and the exposure rows they
are read through. No row here contains a name.

    python -m dosimeter.repository.seeds
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from dosimeter.errors import DosimeterError
from dosimeter.logging_config import configure_logging, get_logger
from dosimeter.repository import queries
from dosimeter.repository.connection import session_scope
from dosimeter.repository.models import DistrictGrant, Exposure, WorkerDoseRecord

_LOGGER = get_logger(__name__)

# Update if the packet is built with a different id.
P4_WORKER_ID = "WKR-1047"

OFFICER_DISTRICTS: dict[str, tuple[str, ...]] = {
    "OFF-101": ("District 1", "District 2"),
    "OFF-102": ("District 3",),
    "OFF-103": ("District 4",),
}

# OFF-104 exists with no grant at all, so the denial path has something to run against.
UNGRANTED_OFFICER = "OFF-104"

EXPOSURES: tuple[Exposure, ...] = (
    Exposure(
        id="exp-0411",
        worker_id="WKR-1047",
        district="District 1",
        occurred_on=date(2026, 3, 12),
        status="seeded",
    ),
    Exposure(
        id="exp-0412",
        worker_id="WKR-1047",
        district="District 2",
        occurred_on=date(2026, 6, 18),
        status="seeded",
    ),
    Exposure(
        id="exp-0413",
        worker_id="WKR-1048",
        district="District 3",
        occurred_on=date(2026, 7, 9),
        status="seeded",
    ),
    # Only OFF-103 holds District 4, so this one is readable by its owning officer alone.
    Exposure(
        id="exp-0414",
        worker_id=P4_WORKER_ID,
        district="District 4",
        occurred_on=date(2026, 8, 21),
        status="seeded",
    ),
)

WORKER_DOSE_HISTORY: tuple[WorkerDoseRecord, ...] = (
    WorkerDoseRecord(
        worker_id=P4_WORKER_ID,
        quantity="planned_special_exposure_lifetime",
        value=6.0,
        unit="rem",
        as_of=date(2025, 11, 4),
        note="prior lifetime planned special exposure dose, read by R4",
    ),
    WorkerDoseRecord(
        worker_id="WKR-1047",
        quantity="tede_year_to_date",
        value=1.2,
        unit="rem",
        as_of=date(2026, 1, 1),
    ),
    WorkerDoseRecord(
        worker_id="WKR-1048",
        quantity="tede_year_to_date",
        value=0.4,
        unit="rem",
        as_of=date(2026, 1, 1),
    ),
)


def apply_seeds(session: Session) -> dict[str, int]:
    """Insert the seed rows. Running it twice changes nothing."""

    for officer_code, districts in OFFICER_DISTRICTS.items():
        officer = queries.upsert_officer(session, officer_code)
        for district in districts:
            queries.add_grant(session, DistrictGrant(officer_id=officer.id, district=district))

    queries.upsert_officer(session, UNGRANTED_OFFICER)

    for exposure in EXPOSURES:
        queries.insert_exposure(session, exposure)

    for record in WORKER_DOSE_HISTORY:
        queries.upsert_worker_dose_record(session, record)

    session.commit()
    return {
        "officers": len(OFFICER_DISTRICTS) + 1,
        "grants": sum(len(districts) for districts in OFFICER_DISTRICTS.values()),
        "exposures": len(EXPOSURES),
        "worker_dose_records": len(WORKER_DOSE_HISTORY),
    }


def main() -> int:
    configure_logging()
    try:
        with session_scope() as session:
            counts = apply_seeds(session)
    except DosimeterError as error:
        _LOGGER.error("seeds.failed", extra={"detail": str(error)})
        return 1
    _LOGGER.info("seeds.applied", extra=counts)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
