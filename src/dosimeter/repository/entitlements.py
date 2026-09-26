"""
Who is allowed to read what. An officer holds grants over districts, and a call
without a grant gets a denial object back, never an empty list.
"""

from sqlalchemy.orm import Session

from dosimeter.repository import queries
from dosimeter.repository.models import (
    EntitlementDenial,
    Exposure,
    ReviewQueueItem,
    SimilarExposure,
)

UNKNOWN_OFFICER = "unknown_officer"
NO_GRANTS = "no_grants"
DISTRICT_NOT_GRANTED = "district_not_granted"


def granted_districts(session: Session, officer_code: str) -> list[str]:
    """Districts this officer may read."""

    return queries.districts_for_officer(session, officer_code)


def _denial(officer_code: str, reason_code: str, message: str, district: str | None = None):
    return EntitlementDenial(
        reason_code=reason_code,
        message=message,
        officer_code=officer_code,
        district=district,
    )


def check_officer(
    session: Session,
    officer_code: str,
) -> list[str] | EntitlementDenial:
    """The officer's districts, or a denial explaining why there are none."""

    if queries.officer_by_code(session, officer_code) is None:
        return _denial(officer_code, UNKNOWN_OFFICER, "no officer with that code")

    districts = granted_districts(session, officer_code)
    if not districts:
        return _denial(officer_code, NO_GRANTS, "this officer holds no district grants")
    return districts


def exposure_for_officer(
    session: Session,
    officer_code: str,
    exposure_id: str,
) -> Exposure | EntitlementDenial | None:
    districts = check_officer(session, officer_code)
    if isinstance(districts, EntitlementDenial):
        return districts

    exposure = queries.get_exposure(session, exposure_id)
    if exposure is None:
        return None
    if exposure.district not in districts:
        return _denial(
            officer_code,
            DISTRICT_NOT_GRANTED,
            "this officer holds no grant on that district",
            district=exposure.district,
        )
    return exposure


def review_queue_for_officer(
    session: Session,
    officer_code: str,
) -> list[ReviewQueueItem] | EntitlementDenial:
    districts = check_officer(session, officer_code)
    if isinstance(districts, EntitlementDenial):
        return districts
    return queries.list_review_queue(session, districts)


def similar_exposures_for_officer(
    session: Session,
    officer_code: str,
    embedding: list[float],
    query_text: str = "",
    limit: int = 5,
) -> list[SimilarExposure] | EntitlementDenial:
    districts = check_officer(session, officer_code)
    if isinstance(districts, EntitlementDenial):
        return districts
    return queries.find_similar_exposures(session, embedding, districts, query_text, limit)
