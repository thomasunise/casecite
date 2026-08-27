"""Static court list for jurisdiction pickers.

Replaces the court_rules table of the former standalone SQLite reference
database (``services/document_db``). The entries and their order are exactly
what ``SELECT DISTINCT court_id, court_name, jurisdiction_type FROM court_rules
ORDER BY jurisdiction_type, court_name`` returned from the old seeder, so the
``GET /legal-docs/courts`` payload is unchanged.
"""

COURTS: list[dict[str, str]] = [
    {
        "court_id": "cacd",
        "court_name": "Central District of California",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "caed",
        "court_name": "Eastern District of California",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "nyed",
        "court_name": "Eastern District of New York",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "federal-generic",
        "court_name": "Federal Court (Generic)",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "cand",
        "court_name": "Northern District of California",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "casd",
        "court_name": "Southern District of California",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "nysd",
        "court_name": "Southern District of New York",
        "jurisdiction_type": "federal",
    },
    {
        "court_id": "cadc",
        "court_name": "DC Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca8",
        "court_name": "Eighth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca11",
        "court_name": "Eleventh Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "cafc",
        "court_name": "Federal Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca5",
        "court_name": "Fifth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca1",
        "court_name": "First Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca4",
        "court_name": "Fourth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca9",
        "court_name": "Ninth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca2",
        "court_name": "Second Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca7",
        "court_name": "Seventh Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca6",
        "court_name": "Sixth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca10",
        "court_name": "Tenth Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "ca3",
        "court_name": "Third Circuit Court of Appeals",
        "jurisdiction_type": "federal_appellate",
    },
    {
        "court_id": "az-superior",
        "court_name": "Arizona Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "ca-superior",
        "court_name": "California Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "co-district",
        "court_name": "Colorado District Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "fl-circuit",
        "court_name": "Florida Circuit Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "ga-superior",
        "court_name": "Georgia Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "il-circuit",
        "court_name": "Illinois Circuit Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "ma-superior",
        "court_name": "Massachusetts Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "nv-district",
        "court_name": "Nevada District Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "nj-superior",
        "court_name": "New Jersey Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "ny-supreme",
        "court_name": "New York Supreme Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "pa-common-pleas",
        "court_name": "Pennsylvania Court of Common Pleas",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "tx-district",
        "court_name": "Texas District Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "wa-superior",
        "court_name": "Washington Superior Court",
        "jurisdiction_type": "state",
    },
    {
        "court_id": "ca-appellate",
        "court_name": "California Court of Appeal",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "fl-dca",
        "court_name": "Florida District Court of Appeal",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "ga-appeals",
        "court_name": "Georgia Court of Appeals",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "il-appellate",
        "court_name": "Illinois Appellate Court",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "ny-appellate",
        "court_name": "New York Appellate Division",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "pa-superior",
        "court_name": "Pennsylvania Superior Court",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "tx-appeals",
        "court_name": "Texas Court of Appeals",
        "jurisdiction_type": "state_appellate",
    },
    {
        "court_id": "ca-supreme",
        "court_name": "California Supreme Court",
        "jurisdiction_type": "state_supreme",
    },
]


def get_all_courts() -> list[dict[str, str]]:
    """Return the courts available in jurisdiction pickers (copies, safe to mutate)."""
    return [dict(court) for court in COURTS]
