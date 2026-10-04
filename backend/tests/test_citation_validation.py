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


class TestWrongCaseGuards:
    """The check must never report on a case other than the one asked about."""

    @pytest.mark.asyncio
    async def test_name_query_does_not_accept_an_unrelated_first_hit(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock()
        unrelated = [{**FOUND[0], "caseName": "Doe v. Bolton", "caseNameShort": "Doe"}]
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(unrelated)):
            result = await svc.validate_citation("Roe v. Wade")
        assert result.analysis_basis == "not_found"
        assert result.is_good_law is None
        assert "Doe v. Bolton" in result.notes[0]
        svc.get_citing_opinions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_name_query_picks_the_matching_result_not_the_first(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(1, CitationTreatment.POSITIVE)], []]
        )
        results = [
            {**FOUND[0], "cluster_id": 1, "caseName": "Doe v. Bolton", "caseNameShort": "Doe"},
            FOUND[0],
        ]
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(results)):
            result = await svc.validate_citation("Roe v. Wade")
        assert result.case_id == 108713
        assert result.case_name == "Roe v. Wade"

    @pytest.mark.asyncio
    async def test_citation_query_requires_the_reporter_cite_to_match(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock()
        other = [{**FOUND[0], "citation": ["410 U.S. 179"]}]
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(other)):
            result = await svc.validate_citation("410 U.S. 113")
        assert result.analysis_basis == "not_found"
        svc.get_citing_opinions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_citation_match_tolerates_spacing_and_a_full_cite(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(
            side_effect=[[_citing(1, CitationTreatment.POSITIVE)], []]
        )
        spaced = [{**FOUND[0], "citation": ["410 U. S. 113"]}]
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(spaced)):
            result = await svc.validate_citation("Roe v. Wade, 410 U.S. 113 (1973)")
        assert result.case_id == 108713

    @pytest.mark.asyncio
    async def test_search_result_opinion_ids_are_used_for_the_cites_query(self):
        svc = _svc()
        svc.get_citing_opinions = AsyncMock(side_effect=[[], []])
        found = [{**FOUND[0], "opinions": [{"id": 9001}, {"id": 9002}]}]
        with patch("app.services.courtlistener.cl_client", return_value=_search_client(found)):
            await svc.validate_citation("410 U.S. 113")
        assert svc.get_citing_opinions.await_args_list[0].kwargs["opinion_ids"] == [9001, 9002]

    @pytest.mark.asyncio
    async def test_unresolvable_cluster_is_could_not_verify_not_a_wrong_case_scan(self):
        """When the cluster's opinions cannot be resolved, no ``cites:`` search
        may run with the cluster id standing in for an opinion id."""
        svc = _svc()

        search_resp = MagicMock(status_code=200)
        search_resp.json.return_value = {"results": FOUND}
        cluster_resp = MagicMock(status_code=403)
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[search_resp, cluster_resp])
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.courtlistener.cl_client", return_value=cm):
            result = await svc.validate_citation("410 U.S. 113")

        assert result.analysis_basis == "citing_lookup_failed"
        assert result.warning_level == "unknown"
        assert result.is_good_law is None
        assert any("Could not verify" in n for n in result.notes)
        # Only the case search and the cluster lookup ran — no cites: search.
        assert client.get.await_count == 2
        assert all("cites:" not in str(c) for c in client.get.await_args_list)


class TestSharedClient:
    def test_all_three_services_share_token_handling_and_courts(self):
        from app.services.courtlistener_client import CourtListenerClientBase
        from app.services.judge_intel import JudgeIntelService
        from app.services.legal_tools import LegalToolsService

        for cls in (CourtListenerService, LegalToolsService, JudgeIntelService):
            assert issubclass(cls, CourtListenerClientBase)
            service = cls()
            service.set_token("  tok  ")
            assert service.headers["Authorization"] == "Token   tok  "
            service.set_token("")
            assert service.api_token is None
            assert "Authorization" not in service.headers
            with pytest.raises(ValueError, match="token required"):
                service._check_token()
            assert service._get_courts_for_jurisdiction("california") == ["cal", "calctapp"]
            assert str(service._parse_date("2024-03-05T10:00:00Z")) == "2024-03-05"
