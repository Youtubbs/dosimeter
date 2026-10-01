"""
Seed officers, district grants, worker dose histories and the exposure rows they
are read through. No row here contains a name.

    python -m dosimeter.repository.seeds
"""

import logging
from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from dosimeter.errors import DosimeterError
from dosimeter.logging_config import configure_logging
from dosimeter.repository import queries
from dosimeter.repository.connection import session_scope
from dosimeter.repository.models import DistrictGrant, Exposure, HistoricalExposure, WorkerDoseRecord

logger = logging.getLogger(__name__)

# Update if the packet is built with a different id.
P4_WORKER_ID = "WKR-1047"

OFFICER_DISTRICTS: dict[str, tuple[str, ...]] = {
    "OFF-101": ("District 1", "District 2"),
    # Two officers over District 2, so an approval can come from someone other
    # than the officer who ran the assessment.
    "OFF-102": ("District 2", "District 3"),
    "OFF-103": ("District 4",),
}

# OFF-104 exists with no grant at all, so the denial path has something to run against.
UNGRANTED_OFFICER = "OFF-104"

EXPOSURES: tuple[Exposure, ...] = (
    Exposure(
        id="EXP-2026-0411",
        worker_id="WKR-1047",
        district="District 1",
        occurred_on=date(2026, 3, 12),
        status="seeded",
    ),
    Exposure(
        id="EXP-2026-0412",
        worker_id="WKR-1047",
        district="District 2",
        occurred_on=date(2026, 6, 18),
        status="seeded",
    ),
    Exposure(
        id="EXP-2026-0413",
        worker_id="WKR-1048",
        district="District 3",
        occurred_on=date(2026, 7, 9),
        status="seeded",
    ),
    # Only OFF-103 holds District 4, so this one is readable by its owning officer alone.
    Exposure(
        id="EXP-2026-0414",
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


# Seeded precedent for find_similar_exposures. one record each side of the R1 and R2
# limits for each dose quantity, two equipment failures, and two messy records.
HISTORICAL_EXPOSURES: tuple[HistoricalExposure, ...] = (
    HistoricalExposure(
        exposure_id="hist-r1-tede-above",
        worker_id="WKR-2001",
        district="District 1",
        occurred_on=date(2024, 2, 14),
        outcome="immediate_notification",
        deciding_rule="R1",
        narrative="Radiographer stayed at the crank during a 40-minute shot after the collimator was left off. Dosimeter processed at 26 rem TEDE.",
        normalized_fields={'tede': '26 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r1-tede-below",
        worker_id="WKR-2002",
        district="District 2",
        occurred_on=date(2024, 3, 2),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Assistant entered the restricted area during exposure to clear a stuck film holder. Badge read 24 rem TEDE, under the immediate tier.",
        normalized_fields={'tede': '24 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r1-lens-above",
        worker_id="WKR-2003",
        district="District 3",
        occurred_on=date(2024, 4, 19),
        outcome="immediate_notification",
        deciding_rule="R1",
        narrative="Worker leaned over an open camera port to inspect the guide tube connector. Lens dose equivalent estimated at 80 rem.",
        normalized_fields={'lens': '80 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r1-lens-below",
        worker_id="WKR-2004",
        district="District 4",
        occurred_on=date(2024, 5, 7),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Eye-level viewing of the source window during a crank check. Lens dose equivalent reconstructed at 70 rem.",
        normalized_fields={'lens': '70 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r1-shallow-above",
        worker_id="WKR-2005",
        district="District 1",
        occurred_on=date(2024, 6, 11),
        outcome="immediate_notification",
        deciding_rule="R1",
        narrative="Radiographer picked up a disconnected source pigtail by hand before recognizing it. Extremity shallow dose 260 rad.",
        normalized_fields={'shallow': '260 rad extremity'},
    ),
    HistoricalExposure(
        exposure_id="hist-r1-shallow-below",
        worker_id="WKR-2006",
        district="District 2",
        occurred_on=date(2024, 7, 23),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Hand briefly touched the drive cable end fitting while the source was exposed. Extremity shallow dose 240 rad.",
        normalized_fields={'shallow': '240 rad extremity'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-tede-above",
        worker_id="WKR-2007",
        district="District 3",
        occurred_on=date(2024, 8, 30),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Survey meter battery failed and the crew worked a second shift without a working rate alarm. TEDE 5.4 rem.",
        normalized_fields={'tede': '5.4 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-tede-below",
        worker_id="WKR-2008",
        district="District 4",
        occurred_on=date(2024, 9, 16),
        outcome="no_report",
        deciding_rule="R2",
        narrative="Long weld-inspection campaign with repeated close approaches. Quarterly TEDE 4.6 rem, below the 24-hour tier.",
        normalized_fields={'tede': '4.6 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-lens-above",
        worker_id="WKR-2009",
        district="District 1",
        occurred_on=date(2024, 10, 4),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Worker repositioned the collimator by eye without shielding glasses. Lens dose equivalent 16 rem.",
        normalized_fields={'lens': '16 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-lens-below",
        worker_id="WKR-2010",
        district="District 2",
        occurred_on=date(2024, 11, 12),
        outcome="no_report",
        deciding_rule="R2",
        narrative="Routine setup with the camera at chest height; lens dose equivalent 14 rem for the quarter.",
        normalized_fields={'lens': '14 rem'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-shallow-above",
        worker_id="WKR-2011",
        district="District 3",
        occurred_on=date(2024, 12, 3),
        outcome="24_hour_notification",
        deciding_rule="R2",
        narrative="Glove contaminated while handling a damaged source holder. Skin shallow dose 52 rem.",
        normalized_fields={'shallow': '52 rem skin'},
    ),
    HistoricalExposure(
        exposure_id="hist-r2-shallow-below",
        worker_id="WKR-2012",
        district="District 4",
        occurred_on=date(2025, 1, 21),
        outcome="no_report",
        deciding_rule="R2",
        narrative="Skin contact with a contaminated hose fitting during cleanup. Skin shallow dose 47 rem.",
        normalized_fields={'shallow': '47 rem skin'},
    ),
    HistoricalExposure(
        exposure_id="hist-equipment-retract",
        worker_id="WKR-2013",
        district="District 2",
        occurred_on=date(2025, 2, 27),
        outcome="equipment_report",
        deciding_rule="34.101(a)(2)",
        narrative="The source assembly would not retract to its fully shielded position. The crew withdrew, surveyed the boundary and called the RSO. TEDE 0.8 rem.",
        normalized_fields={'tede': '0.8 rem', 'equipment': 'inability to retract'},
    ),
    HistoricalExposure(
        exposure_id="hist-equipment-cable",
        worker_id="WKR-2014",
        district="District 4",
        occurred_on=date(2025, 3, 18),
        outcome="equipment_report",
        deciding_rule="34.101(a)(2)",
        narrative="Drive cable kinked and the source stuck in the guide tube for 12 minutes before it could be cranked back. TEDE 1.1 rem.",
        normalized_fields={'tede': '1.1 rem', 'equipment': 'source stuck in guide tube'},
    ),
    HistoricalExposure(
        exposure_id="hist-messy-units",
        worker_id="WKR-2015",
        district="District 1",
        occurred_on=date(2025, 4, 9),
        outcome="no_report",
        deciding_rule="R2",
        narrative="Dosimetry report lists 30 mSv with a handwritten correction to 3 rem TEDE; the vendor confirmed 3 rem.",
        normalized_fields={'tede': '30 mSv (3 rem)'},
    ),
    HistoricalExposure(
        exposure_id="hist-insufficient",
        worker_id="WKR-2016",
        district="District 3",
        occurred_on=date(2025, 5, 14),
        outcome="insufficient_data",
        deciding_rule="R5",
        narrative="Badge lost in the field and no dose estimate recorded. The crew log only says the source was exposed longer than planned.",
        normalized_fields={},
    ),
)


def apply_seeds(session: Session, embed: Callable[[str], list[float]] | None = None) -> dict[str, int]:
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

    for record in HISTORICAL_EXPOSURES:
        queries.insert_historical_exposure(session, record)

    embedded = 0
    if embed is not None:
        try:
            for record in queries.historical_exposures_missing_embedding(session):
                queries.insert_historical_exposure(session, record, embedding=embed(record.narrative))
                embedded += 1
        except Exception as error:  # without model access the rows stay; seeding again later embeds them
            logger.warning("seeds.embedding_skipped", extra={"detail": str(error)})

    session.commit()
    return {
        "officers": len(OFFICER_DISTRICTS) + 1,
        "grants": sum(len(districts) for districts in OFFICER_DISTRICTS.values()),
        "exposures": len(EXPOSURES),
        "worker_dose_records": len(WORKER_DOSE_HISTORY),
        "historical_exposures": len(HISTORICAL_EXPOSURES),
        "embedded": embedded,
    }


def main() -> int:
    # the repository layer does not otherwise depend on the model layer
    from dosimeter.models.bedrock import embed_text

    configure_logging()
    try:
        with session_scope() as session:
            counts = apply_seeds(session, embed=embed_text)
    except DosimeterError as error:
        logger.error("seeds.failed", extra={"detail": str(error)})
        return 1
    logger.info("seeds.applied", extra=counts)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
