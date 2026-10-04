"""
Jurisdiction-rule seed data.

Each entry is a structured rule about how a clause is treated in a specific
state / federal jurisdiction. The schema scales — additional jurisdictions
and clauses can be added without code changes.

Enforceability values:
    enforceable  — clause is valid as drafted
    limited      — valid only with specific limits (see constraints)
    void         — unenforceable as drafted
    reformable   — court may blue-pencil to make enforceable
    unsettled    — law unclear; flag for attorney review

These rules are a drafting aid, not legal advice, and law changes. Every rule
carries ``as_of`` (when this data was compiled) and says so in its note.

Numbers appear in ``constraints`` only where a statute sets them. Where courts
apply a reasonableness standard with no statutory figure, the constraint says
so in words — a made-up cap would read as a bright line that does not exist.
Statutory figures that the statute itself adjusts over time are listed under
``verify_current_figures`` and must be checked before use.
"""

# When this data was compiled. It has not been re-verified since.
RULES_AS_OF = "2024"

JURISDICTION_RULES: list[dict] = [
    # =========================================================================
    # NON-COMPETE — the canonical jurisdiction-variance clause
    # =========================================================================
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "CA",
        "enforceability": "void",
        "constraints": {
            "ban_basis": "statute",
            "exceptions": [
                "sale_of_business",
                "dissolution_of_partnership",
                "dissolution_of_llc",
            ],
        },
        "authorities": [
            {"type": "statute", "cite": "Cal. Bus. & Prof. Code § 16600"},
            {"type": "statute", "cite": "Cal. Bus. & Prof. Code § 16600.1"},
            {
                "type": "case",
                "cite": "Edwards v. Arthur Andersen LLP, 44 Cal. 4th 937 (2008)",
            },
        ],
        "note": "California voids most non-competes, including narrow ones; only sale-of-business and entity-dissolution exceptions apply.",
        "recommended_text": (
            "[Non-compete intentionally omitted — unenforceable in California under "
            "Cal. Bus. & Prof. Code § 16600. Use confidentiality and "
            "non-solicit-of-customers obligations only.]"
        ),
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "ND",
        "enforceability": "void",
        "constraints": {"ban_basis": "statute"},
        "authorities": [{"type": "statute", "cite": "N.D. Cent. Code § 9-08-06"}],
        "note": "North Dakota statutorily voids most non-competes, with limited sale-of-business exception.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "OK",
        "enforceability": "void",
        "constraints": {"ban_basis": "statute"},
        "authorities": [{"type": "statute", "cite": "Okla. Stat. tit. 15, § 219A"}],
        "note": "Oklahoma generally voids non-competes; allows narrow non-solicit of established customers.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "MN",
        "enforceability": "void",
        "constraints": {"ban_basis": "statute_post_2023"},
        "authorities": [{"type": "statute", "cite": "Minn. Stat. § 181.988"}],
        "note": "Minnesota voids new employee non-competes entered into on/after July 1, 2023.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "TX",
        "enforceability": "limited",
        "constraints": {
            "duration": "reasonable — no statutory cap",
            "geographic_scope": "reasonable",
            "scope_must_match_consideration": True,
            "ancillary_to_otherwise_enforceable_agreement": True,
            "blue_pencil_allowed": True,
        },
        "authorities": [
            {"type": "statute", "cite": "Tex. Bus. & Com. Code § 15.50"},
            {
                "type": "case",
                "cite": "Marsh USA Inc. v. Cook, 354 S.W.3d 764 (Tex. 2011)",
            },
        ],
        "note": "Texas requires the non-compete be ancillary to an otherwise enforceable agreement and reasonable in scope, time, and geography. Courts may reform overbroad covenants.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "FL",
        "enforceability": "enforceable",
        "constraints": {
            "presumed_reasonable_up_to_months_employee": 6,
            "presumed_unreasonable_over_months_employee": 24,
            "presumed_unreasonable_over_months_sale": 84,
            "presumptions_are_rebuttable": True,
            "blue_pencil_allowed": True,
        },
        "authorities": [{"type": "statute", "cite": "Fla. Stat. § 542.335"}],
        "note": "Florida is one of the most employer-friendly states; the statute sets rebuttable presumptions of reasonableness by duration (not hard caps) and authorizes modification.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "MA",
        "enforceability": "limited",
        "constraints": {
            "max_duration_months": 12,
            "garden_leave_required": True,
            "garden_leave_min_pct": 50,
            "advance_notice_days": 10,
            "right_to_counsel_notice": True,
        },
        "authorities": [{"type": "statute", "cite": "Mass. Gen. Laws ch. 149, § 24L"}],
        "note": "Massachusetts requires garden leave (min 50% base salary) or other mutually agreed consideration plus written notice with right to counsel.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "WA",
        "enforceability": "limited",
        "constraints": {
            "min_annual_earnings_employee": 120559,
            "min_annual_earnings_contractor": 301399,
            "earnings_thresholds_year": 2024,
            "verify_current_figures": [
                "min_annual_earnings_employee",
                "min_annual_earnings_contractor",
            ],
            "presumed_unreasonable_over_months": 18,
            "advance_disclosure_required": True,
        },
        "authorities": [{"type": "statute", "cite": "Wash. Rev. Code § 49.62"}],
        "note": "Washington requires earnings thresholds, advance disclosure, and presumes a duration over 18 months unreasonable. The earnings thresholds are adjusted every year; the figures recorded here are the 2024 amounts — verify the current figure.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "IL",
        "enforceability": "limited",
        "constraints": {
            "min_annual_earnings": 75000,
            "verify_current_figures": ["min_annual_earnings"],
            "consideration_period_years": 2,
            "advance_notice_days": 14,
            "blue_pencil_allowed": True,
        },
        "authorities": [{"type": "statute", "cite": "Illinois Freedom to Work Act, 820 ILCS 90"}],
        "note": "Illinois requires an income threshold for non-competes ($75k when the Act took effect; the statute raises it on a schedule — verify the current figure), 14 days advance review, and either continued employment for 2+ years or other adequate consideration.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "DE",
        "enforceability": "limited",
        "constraints": {
            "duration": "reasonable — no statutory cap",
            "blue_pencil_allowed": True,
            "geographic_scope": "reasonable",
        },
        "authorities": [
            {
                "type": "case",
                "cite": "Tristate Courier & Carriage, Inc. v. Berryman, 2004 WL 835886 (Del. Ch.)",
            }
        ],
        "note": "Delaware enforces reasonable non-competes; Chancery Court may blue-pencil overbroad scope.",
    },
    {
        "canonical_slug": "non_compete",
        "jurisdiction": "NY",
        "enforceability": "limited",
        "constraints": {
            "duration": "reasonable — no statutory cap",
            "legitimate_business_interest_required": True,
            "no_undue_hardship_on_employee": True,
            "blue_pencil_allowed": True,
        },
        "authorities": [
            {
                "type": "case",
                "cite": "BDO Seidman v. Hirshberg, 93 N.Y.2d 382 (1999)",
            }
        ],
        "note": "New York's BDO Seidman three-prong test: legitimate interest, no undue hardship, not injurious to public.",
    },
    # =========================================================================
    # NON-SOLICIT — generally enforced more leniently than non-competes
    # =========================================================================
    {
        "canonical_slug": "non_solicit",
        "jurisdiction": "CA",
        "enforceability": "limited",
        "constraints": {
            "employee_non_solicit": "void",
            "customer_non_solicit": "void_unless_trade_secret",
        },
        "authorities": [
            {"type": "statute", "cite": "Cal. Bus. & Prof. Code § 16600"},
            {
                "type": "case",
                "cite": "AMN Healthcare, Inc. v. Aya Healthcare Services, Inc., 28 Cal. App. 5th 923 (2018)",
            },
        ],
        "note": "California treats employee non-solicits as void post-AMN; customer non-solicits void unless protecting actual trade secrets.",
    },
    {
        "canonical_slug": "non_solicit",
        "jurisdiction": "TX",
        "enforceability": "enforceable",
        "constraints": {
            "duration": "reasonable — no statutory cap",
            "blue_pencil_allowed": True,
        },
        "authorities": [{"type": "statute", "cite": "Tex. Bus. & Com. Code § 15.50"}],
        "note": "Texas treats non-solicits like non-competes — must be reasonable and ancillary.",
    },
    # =========================================================================
    # JURY WAIVER
    # =========================================================================
    {
        "canonical_slug": "jury_waiver",
        "jurisdiction": "CA",
        "enforceability": "void",
        "constraints": {"contractual_pre_dispute_jury_waiver": "void"},
        "authorities": [
            {
                "type": "case",
                "cite": "Grafton Partners L.P. v. Superior Court, 36 Cal. 4th 944 (2005)",
            }
        ],
        "note": "California voids pre-dispute contractual jury waivers; arbitration is the alternative.",
    },
    {
        "canonical_slug": "jury_waiver",
        "jurisdiction": "GA",
        "enforceability": "void",
        "constraints": {"contractual_pre_dispute_jury_waiver": "void"},
        "authorities": [
            {
                "type": "case",
                "cite": "Bank S., N.A. v. Howard, 264 Ga. 339 (1994)",
            }
        ],
        "note": "Georgia generally voids contractual pre-dispute jury waivers.",
    },
    {
        "canonical_slug": "jury_waiver",
        "jurisdiction": "DE",
        "enforceability": "enforceable",
        "constraints": {"must_be_knowing_and_voluntary": True, "conspicuous_required": True},
        "authorities": [],
        "note": "Delaware enforces conspicuous, knowing, voluntary jury waivers.",
    },
    {
        "canonical_slug": "jury_waiver",
        "jurisdiction": "NY",
        "enforceability": "enforceable",
        "constraints": {"must_be_knowing_and_voluntary": True, "conspicuous_required": True},
        "authorities": [],
        "note": "New York enforces jury waivers if knowing and voluntary; conspicuousness matters.",
    },
    {
        "canonical_slug": "jury_waiver",
        "jurisdiction": "TX",
        "enforceability": "enforceable",
        "constraints": {"must_be_knowing_and_voluntary": True},
        "authorities": [
            {
                "type": "case",
                "cite": "In re Prudential Ins. Co. of Am., 148 S.W.3d 124 (Tex. 2004)",
            }
        ],
        "note": "Texas Supreme Court enforces knowing/voluntary waivers.",
    },
    # =========================================================================
    # ARBITRATION CLASS WAIVER
    # =========================================================================
    {
        "canonical_slug": "arbitration",
        "jurisdiction": "CA",
        "enforceability": "limited",
        "constraints": {
            "PAGA_claims_non_waivable": True,
            "consumer_friendly_rules_required": True,
            "fees_must_be_borne_by_employer_in_employment": True,
        },
        "authorities": [
            {
                "type": "case",
                "cite": "Armendariz v. Foundation Health Psychcare Servs., Inc., 24 Cal. 4th 83 (2000)",
            },
            {
                "type": "case",
                "cite": "Adolph v. Uber Technologies, 14 Cal. 5th 1104 (2023)",
            },
        ],
        "note": "California requires Armendariz factors for employment arbitration; PAGA representative claims cannot be fully waived.",
    },
    {
        "canonical_slug": "arbitration",
        "jurisdiction": "US-FED",
        "enforceability": "limited",
        "constraints": {
            "sexual_harassment_assault_non_arbitrable": True,
        },
        "authorities": [
            {
                "type": "statute",
                "cite": "Ending Forced Arbitration of Sexual Assault and Sexual Harassment Act of 2021 (9 U.S.C. § 402)",
            }
        ],
        "note": "Federal law makes pre-dispute arbitration of sexual-harassment/assault claims unenforceable at the claimant's election.",
    },
    # =========================================================================
    # LIMITATION OF LIABILITY — gross negligence carveouts
    # =========================================================================
    {
        "canonical_slug": "limitation_of_liability",
        "jurisdiction": "NY",
        "enforceability": "limited",
        "constraints": {
            "cannot_limit_gross_negligence": True,
            "cannot_limit_intentional_misconduct": True,
            "cannot_limit_fraud": True,
        },
        "authorities": [
            {
                "type": "case",
                "cite": "Kalisch-Jarcho, Inc. v. City of New York, 58 N.Y.2d 377 (1983)",
            }
        ],
        "note": "New York voids contractual limitations on liability for gross negligence, willful misconduct, or fraud — these must be carved out.",
    },
    {
        "canonical_slug": "limitation_of_liability",
        "jurisdiction": "CA",
        "enforceability": "limited",
        "constraints": {
            "cannot_limit_willful_injury": True,
            "cannot_limit_violation_of_law": True,
        },
        "authorities": [{"type": "statute", "cite": "Cal. Civ. Code § 1668"}],
        "note": "California voids contracts exempting parties from responsibility for willful injury or violation of law (whether willful or negligent).",
    },
    # =========================================================================
    # WARRANTY DISCLAIMER — UCC formality
    # =========================================================================
    {
        "canonical_slug": "warranty_disclaimer",
        "jurisdiction": "US-FED",
        "enforceability": "limited",
        "constraints": {
            "merchantability_disclaimer_must_mention_word": True,
            "must_be_conspicuous": True,
        },
        "authorities": [{"type": "statute", "cite": "U.C.C. § 2-316"}],
        "note": "Under the UCC, disclaimers of merchantability must mention the word 'merchantability' and be conspicuous (typically all-caps).",
    },
    # =========================================================================
    # GOVERNING LAW — Delaware corporate law preference
    # =========================================================================
    {
        "canonical_slug": "governing_law",
        "jurisdiction": "DE",
        "enforceability": "enforceable",
        "constraints": {
            "minimum_contacts_required_if_DE_chosen_for_non_DE_parties": False,
            "uniform_recognition": True,
        },
        "authorities": [{"type": "statute", "cite": "6 Del. C. § 2708"}],
        "note": "Delaware enforces choice-of-Delaware-law in commercial contracts of $100k+ even without minimum contacts.",
    },
]

# Stamp every rule with when it was compiled, in the structured data and in the
# note (the note is what a reviewer actually reads in a finding).
for _rule in JURISDICTION_RULES:
    _rule["as_of"] = RULES_AS_OF
    _rule["constraints"] = {**_rule.get("constraints", {}), "as_of": RULES_AS_OF}
    _rule["note"] = (
        f"{_rule['note'].rstrip()} (Compiled {RULES_AS_OF}; verify current law before relying on it.)"
    )
