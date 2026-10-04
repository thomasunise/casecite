"""
Legal Tools - Pydantic models and enums.
"""

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class RulingDirection(str, Enum):
    """General direction of a ruling"""

    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    GOVERNMENT = "government"
    INDIVIDUAL = "individual"
    AFFIRMED = "affirmed"
    REVERSED = "reversed"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class JudgeInfo(BaseModel):
    """Federal judge information"""

    id: int
    name: str
    name_full: str | None = None
    court: str | None = None
    court_id: str | None = None
    position: str | None = None
    appointed_by: str | None = None
    date_appointed: date | None = None
    birth_year: int | None = None
    race: str | None = None
    gender: str | None = None
    religion: str | None = None
    law_school: str | None = None
    aba_rating: str | None = None
    is_active: bool = True
    url: str | None = None

    @field_validator("law_school", "aba_rating", mode="before")
    @classmethod
    def convert_list_to_string(cls, v):
        """Convert list values from API to comma-separated string."""
        if isinstance(v, list):
            return ", ".join(str(item) for item in v) if v else None
        return v


class JudgeRulingPattern(BaseModel):
    """Analysis of a judge's ruling patterns"""

    judge_id: int
    judge_name: str
    total_opinions: int
    opinions_analyzed: int

    # Case type breakdown
    case_types: dict[str, int] = {}

    # Ruling tendencies
    ruling_directions: dict[str, int] = {}

    # Topic analysis
    top_topics: list[dict[str, Any]] = []

    # Timeline
    opinions_by_year: dict[int, int] = {}

    # Most cited precedents by this judge
    frequently_cited: list[dict[str, Any]] = []

    # Key statistics
    avg_opinion_length: int | None = None
    reversal_rate: float | None = None  # How often reversed on appeal
    citation_count_avg: float | None = None  # How often their opinions are cited

    # Sample notable cases
    notable_cases: list[dict[str, Any]] = []


class CaseLookupResult(BaseModel):
    """Full case details"""

    id: int
    case_name: str
    case_name_short: str | None = None
    citations: list[str] = []
    court: str
    court_id: str
    date_filed: date | None = None
    date_decided: date | None = None
    docket_number: str | None = None
    judges: str | None = None
    nature_of_suit: str | None = None
    full_text: str | None = None
    html_text: str | None = None
    url: str

    # Citation info
    times_cited: int = 0
    cites_to: list[str] = []  # Cases this opinion cites


class PrecedentResult(BaseModel):
    """A precedent case with citation metrics"""

    id: int
    opinion_id: int | None = None
    case_name: str
    citation: str
    citations: list[str] = []
    court: str
    court_id: str | None = None
    date_filed: date | None = None
    docket_number: str | None = None
    judges: str | None = None
    status: str | None = None
    times_cited: int
    snippet: str | None = None
    url: str


class DocketResult(BaseModel):
    """Court docket information"""

    id: int
    case_name: str
    case_name_full: str | None = None
    docket_number: str
    court: str
    court_id: str | None = None
    date_filed: date | None = None
    date_terminated: date | None = None
    date_argued: date | None = None
    nature_of_suit: str | None = None
    cause: str | None = None
    jury_demand: str | None = None
    jurisdiction_type: str | None = None
    assigned_to: str | None = None
    referred_to: str | None = None
    parties: list[dict[str, str]] = []
    attorneys: list[dict[str, str]] = []
    entry_count: int = 0
    url: str
