"""
Citation check ("validate_citation") — the decision logic, not just the regexes.

The feature is a citing-language scan, so its verdict must never overstate
what a regex over search snippets can know: a single negative hit makes the
answer undetermined, never "good law"; a clean read is claimed only when
passages were actually read; and the most-cited citing opinions are scanned
alongside the most recent ones so an old overruling isn't missed.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.courtlistener import (
    CitationTreatment,
    CitingOpinion,
    CourtListenerService,
)


def _svc() -> CourtListenerService:
    with patch("app.services.courtlistener.settings") as mock_settings:
        mock_settings.courtlistener_api_token = "test-token"
        return CourtListenerService()


def _citing(i: int, treatment: CitationTreatment, found: bool = True) -> CitingOpinion:
    return CitingOpinion(
        id=i,
        case_name=f"Citing Case {i}",
        citation=[f"{100 + i} F.3d 1"],
        court="ca9",
        date_filed=date(2020, 1, min(i, 28)),
        treatment=treatment,
        depth=1,
        snippet="…",
        context_found=found,
        url=None,
    )


def _search_client(results: list[dict]):
    """Async context manager whose .get() returns a search response with `results`."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"results": results}
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


FOUND = [
    {
        "cluster_id": 108713,
        "caseName": "Roe v. Wade",
        "caseNameShort": "Roe",
        "citeCount": 4000,
        "citation": ["410 U.S. 113"],
        "absolute_url": "/opinion/108713/roe-v-wade/",
    }
]


class TestTreatmentVerdict:
    """The threshold matrix, in isolation."""

    @pytest.mark.parametrize(
        "negative,caution,read,level,good",
        [
            (0, 0, 10, "none", True),  # clean read → the only True
            (0, 0, 0, "unknown", None),  # nothing read → not a clean result
            (0, 1, 10, "caution", None),
            (0, 3, 10, "warning", None),
            (1, 0, 10, "warning", None),  # one negative hit is never "good law"
            (2, 0, 10, "warning", None),
            (3, 0, 10, "danger", None),  # never False either — a regex can't know
            (7, 5, 10, "danger", None),
        ],
    )
    def test_matrix(self, negative, caution, read, level, good):
        assert CourtListenerService._treatment_verdict(
            negative=negative, caution=caution, read=read
        ) == (level, good)

    def test_is_never_false(self):
        for negative in range(0, 12):
            for caution in range(0, 6):
                _, good = CourtListenerService._treatment_verdict(
                    negative=negative, caution=caution, read=50
                )
                assert good is not False


class TestValidateCitation:
    @pytest.mark.asyncio
    async def test_one_negative_hit_is_undetermined_not_good_law(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[
                [_citing(1, CitationTreatment.NEGATIVE), _citing(2, CitationTreatment.POSITIVE)],
                [],
            ]
        )
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.warning_level == "warning"
        assert result.is_good_law is None
        assert result.method == "citing_language_scan"
        assert len(result.negative_citations) == 1
        # The caveat frames the result — it is the first note, not the last.
        assert "not an editorial citator" in result.notes[0]

    @pytest.mark.asyncio
    async def test_clean_read_is_good_law(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(1, CitationTreatment.POSITIVE)], []]
        )
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.warning_level == "none"
        assert result.is_good_law is True

    @pytest.mark.asyncio
    async def test_nothing_readable_is_not_a_clean_result(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(1, CitationTreatment.NEUTRAL, found=False)], []]
        )
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.warning_level == "unknown"
        assert result.is_good_law is None
        assert any("no treatment signal" in n for n in result.notes)

    @pytest.mark.asyncio
    async def test_three_negatives_is_danger_but_still_undetermined(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(i, CitationTreatment.NEGATIVE) for i in (1, 2, 3)], []]
        )
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.warning_level == "danger"
        assert result.is_good_law is None

    @pytest.mark.asyncio
    async def test_not_found_is_unknown_not_danger(self):
        svc = _svc()
        with patch("app.services.courtlistener.cl_client", return_value=_search_client([])):
            result = await svc.validate_citation("999 U.S. 999")
        assert result.warning_level == "unknown"
        assert result.is_good_law is None
        assert result.analysis_basis == "not_found"

    @pytest.mark.asyncio
    async def test_most_cited_citing_opinions_are_scanned_too(self):
        """An overruling by a higher court years ago is in the most-cited set,
        not the most-recent 100 — recency alone would have called it clean."""
        svc = _svc()
        recent = [_citing(i, CitationTreatment.POSITIVE) for i in range(1, 6)]
        old_overruling = _citing(99, CitationTreatment.NEGATIVE)
        svc.get_citing_opinions = AsyncMock(side_effect=[recent, [old_overruling, recent[0]]])
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        calls = svc.get_citing_opinions.await_args_list
        assert calls[1].kwargs.get("order_by") == "citeCount desc"
        assert result.warning_level == "warning"
        assert result.is_good_law is None
        # De-duplicated across the two listings.
        assert result.citing_cases_analyzed == 6

    @pytest.mark.asyncio
    async def test_most_cited_failure_does_not_lose_recent_results(self):
        import httpx

        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(1, CitationTreatment.CAUTION)], httpx.ConnectError("boom")]
        )
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(FOUND)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.warning_level == "caution"
        assert result.citing_cases_analyzed == 1
