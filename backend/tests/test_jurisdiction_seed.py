"""
Jurisdiction-rule seed data: dated, and numeric only where a statute sets the number.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.clause_intel.jurisdiction_lookup import evaluate
from app.services.clause_intel.jurisdiction_seed import JURISDICTION_RULES, RULES_AS_OF


def _rule(slug: str, jurisdiction: str) -> dict:
    return next(
        r
        for r in JURISDICTION_RULES
        if r["canonical_slug"] == slug and r["jurisdiction"] == jurisdiction
    )


class TestEveryRuleIsDated:
    def test_as_of_is_on_the_rule_in_its_constraints_and_in_its_note(self):
        assert JURISDICTION_RULES
        for rule in JURISDICTION_RULES:
            assert rule["as_of"] == RULES_AS_OF
            assert rule["constraints"]["as_of"] == RULES_AS_OF
            assert f"Compiled {RULES_AS_OF}" in rule["note"]
            assert "verify current law" in rule["note"]

    def test_one_rule_per_clause_and_jurisdiction(self):
        keys = [(r["canonical_slug"], r["jurisdiction"]) for r in JURISDICTION_RULES]
        assert len(keys) == len(set(keys))


class TestNoInventedBrightLines:
    @pytest.mark.parametrize(
        ("slug", "jurisdiction"),
        [
            ("non_compete", "TX"),
            ("non_compete", "DE"),
            ("non_compete", "NY"),
            ("non_solicit", "TX"),
        ],
    )
    def test_reasonableness_jurisdictions_have_no_numeric_duration_cap(self, slug, jurisdiction):
        constraints = _rule(slug, jurisdiction)["constraints"]
        assert not [k for k in constraints if k.startswith("max_duration")]
        assert "no statutory cap" in constraints["duration"]

    def test_florida_durations_are_presumptions_not_caps(self):
        constraints = _rule("non_compete", "FL")["constraints"]
        assert not [k for k in constraints if k.startswith("max_duration")]
        assert constraints["presumed_unreasonable_over_months_employee"] == 24
        assert constraints["presumptions_are_rebuttable"] is True

    def test_adjusted_statutory_figures_are_flagged_for_verification(self):
        wa = _rule("non_compete", "WA")
        assert set(wa["constraints"]["verify_current_figures"]) == {
            "min_annual_earnings_employee",
            "min_annual_earnings_contractor",
        }
        assert wa["constraints"]["earnings_thresholds_year"] == 2024
        assert "verify the current figure" in wa["note"]

        il = _rule("non_compete", "IL")
        assert il["constraints"]["verify_current_figures"] == ["min_annual_earnings"]
        assert "verify the current figure" in il["note"]

    def test_every_flagged_figure_exists(self):
        for rule in JURISDICTION_RULES:
            for key in rule["constraints"].get("verify_current_figures", []):
                assert key in rule["constraints"]


class TestLookupCarriesTheDate:
    @pytest.mark.asyncio
    async def test_flag_exposes_as_of(self):
        session = MagicMock()
        result = MagicMock()
        result.all.return_value = []  # nothing in the DB → seed fallback
        session.execute = AsyncMock(return_value=result)

        flags = await evaluate(["non_compete"], "ca", session)

        assert len(flags) == 1
        assert flags[0].enforceability == "void"
        assert flags[0].as_of == RULES_AS_OF
        assert f"Compiled {RULES_AS_OF}" in flags[0].note
