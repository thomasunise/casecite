"""
Canonical clause taxonomy seed data.

This is the v1 taxonomy: ~30 widely-used commercial-contract clause types.
Each entry has the structured shape the rest of the engine relies on:

    slug              — stable identifier
    name              — display name
    category          — grouping for UI
    sub_elements      — [{key, name, description, required}]
    market_standard   — baseline body the deviation detector diffs against
    regex_anchors     — high-confidence regex strings (case-insensitive)
    required_keywords — must appear together for a non-embedding partial match

The list deliberately stays compact at v1; the schema scales to 80+
without code changes — content can be added by editing this file.
"""

CANONICAL_CLAUSES: list[dict] = [
    # =========================================================================
    # LIABILITY
    # =========================================================================
    {
        "slug": "limitation_of_liability",
        "name": "Limitation of Liability",
        "category": "liability",
        "description": "Caps and excludes categories of damages.",
        "sub_elements": [
            {
                "key": "aggregate_cap",
                "name": "Aggregate liability cap",
                "description": "Numerical or formulaic cap on total damages.",
                "required": True,
            },
            {
                "key": "consequential_exclusion",
                "name": "Exclusion of consequential damages",
                "description": "Excludes indirect, incidental, special, consequential, lost profits.",
                "required": True,
            },
            {
                "key": "carveouts",
                "name": "Carveouts",
                "description": "Categories not subject to cap (indemnity, IP infringement, gross negligence, fraud, breach of confidentiality).",
                "required": False,
            },
            {
                "key": "mutual",
                "name": "Mutuality",
                "description": "Cap applies to both parties.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "EXCEPT FOR LIABILITY ARISING FROM A PARTY'S INDEMNIFICATION OBLIGATIONS, "
            "BREACH OF CONFIDENTIALITY, OR GROSS NEGLIGENCE OR WILLFUL MISCONDUCT, "
            "(A) IN NO EVENT SHALL EITHER PARTY BE LIABLE TO THE OTHER FOR ANY INDIRECT, "
            "INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR FOR LOST PROFITS, "
            "LOST REVENUE, OR LOSS OF DATA, AND (B) EACH PARTY'S TOTAL AGGREGATE LIABILITY "
            "ARISING OUT OF OR RELATING TO THIS AGREEMENT SHALL NOT EXCEED THE AMOUNTS "
            "PAID OR PAYABLE BY CUSTOMER TO PROVIDER UNDER THIS AGREEMENT IN THE TWELVE "
            "(12) MONTHS PRECEDING THE EVENT GIVING RISE TO THE CLAIM."
        ),
        "regex_anchors": [
            r"limitation of liability",
            r"in no event shall (?:either|any) party be liable",
            r"aggregate liability\s+(?:shall|will)\s+not exceed",
            r"liability\s+(?:cap|cap)",
        ],
        "required_keywords": ["liability", "exceed"],
    },
    {
        "slug": "indemnification",
        "name": "Indemnification",
        "category": "liability",
        "description": "Allocation of third-party claim risk.",
        "sub_elements": [
            {
                "key": "scope",
                "name": "Scope of indemnified claims",
                "description": "Categories: IP infringement, breach, negligence, etc.",
                "required": True,
            },
            {
                "key": "procedure",
                "name": "Indemnification procedure",
                "description": "Notice, control of defense, cooperation, settlement consent.",
                "required": True,
            },
            {
                "key": "exclusive_remedy",
                "name": "Exclusive remedy carveout",
                "description": "Often paired with IP indemnity.",
                "required": False,
            },
            {
                "key": "mutual",
                "name": "Mutual indemnity",
                "description": "Both parties indemnify the other.",
                "required": False,
            },
        ],
        "market_standard_text": (
            'Each party ("Indemnitor") shall defend, indemnify, and hold harmless the other '
            'party and its officers, directors, employees, and agents ("Indemnitees") from '
            "and against any third-party claims, suits, or proceedings, and all related losses, "
            "damages, liabilities, costs, and expenses (including reasonable attorneys' fees), "
            "to the extent arising out of (a) Indemnitor's breach of this Agreement, (b) the "
            "gross negligence or willful misconduct of Indemnitor, or (c) the infringement of "
            "any third-party intellectual property right by Indemnitor's deliverables. "
            "Indemnitee shall (i) promptly notify Indemnitor in writing of the claim, "
            "(ii) give Indemnitor sole control of the defense and settlement, and "
            "(iii) provide reasonable cooperation at Indemnitor's expense. Indemnitor shall "
            "not settle any claim that imposes liability or admission on Indemnitee without "
            "Indemnitee's prior written consent."
        ),
        "regex_anchors": [
            r"indemnif(?:y|ies|ication)",
            r"defend,?\s+indemnify,?\s+and hold harmless",
            r"hold harmless",
        ],
        "required_keywords": ["indemnif", "claim"],
    },
    {
        "slug": "warranty_disclaimer",
        "name": "Warranty Disclaimer",
        "category": "liability",
        "description": "Disclaims implied warranties.",
        "sub_elements": [
            {
                "key": "as_is",
                "name": "AS IS / AS AVAILABLE",
                "description": "Express disclaimer language.",
                "required": True,
            },
            {
                "key": "implied_disclaimed",
                "name": "Implied warranties disclaimed",
                "description": "Merchantability, fitness, non-infringement.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "EXCEPT FOR THE EXPRESS WARRANTIES SET FORTH IN THIS AGREEMENT, THE SERVICES ARE "
            'PROVIDED "AS IS" AND "AS AVAILABLE," AND PROVIDER DISCLAIMS ALL OTHER WARRANTIES, '
            "WHETHER EXPRESS, IMPLIED, OR STATUTORY, INCLUDING ANY IMPLIED WARRANTIES OF "
            "MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT."
        ),
        "regex_anchors": [
            r"\bAS IS\b",
            r"disclaims?\s+all\s+(?:other\s+)?warranties",
            r"merchantability",
            r"fitness for (?:a particular|the intended) purpose",
        ],
        "required_keywords": ["warrant", "disclaim"],
    },
    # =========================================================================
    # IP
    # =========================================================================
    {
        "slug": "ip_assignment",
        "name": "IP Assignment",
        "category": "ip",
        "description": "Transfers ownership of created IP.",
        "sub_elements": [
            {
                "key": "present_assignment",
                "name": "Present-tense assignment",
                "description": "'hereby assigns' rather than 'agrees to assign'.",
                "required": True,
            },
            {
                "key": "scope",
                "name": "Scope of assignment",
                "description": "Deliverables, work product, related IP rights.",
                "required": True,
            },
            {
                "key": "moral_rights_waiver",
                "name": "Moral rights waiver",
                "description": "Waiver to extent permitted by law.",
                "required": False,
            },
            {
                "key": "further_assurances",
                "name": "Further assurances",
                "description": "Obligation to execute confirmatory documents.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Provider hereby irrevocably assigns to Customer all right, title, and interest, "
            "including all intellectual property rights, in and to the Deliverables and any "
            "derivative works thereof. To the extent any such rights cannot be assigned by law, "
            "Provider hereby grants Customer a perpetual, worldwide, royalty-free, exclusive "
            "license to use, reproduce, modify, and distribute such rights. Provider waives any "
            "moral rights in the Deliverables to the maximum extent permitted by applicable law."
        ),
        "regex_anchors": [
            r"hereby (?:irrevocably )?assigns?",
            r"work(?:s)? made for hire",
            r"assignment of (?:intellectual property|all right)",
        ],
        "required_keywords": ["assign", "right"],
    },
    {
        "slug": "ip_license",
        "name": "IP License Grant",
        "category": "ip",
        "description": "Grant of license rights to IP.",
        "sub_elements": [
            {
                "key": "scope_grant",
                "name": "Scope: exclusive/non-exclusive, sublicensable, transferable",
                "description": "Foundational license parameters.",
                "required": True,
            },
            {
                "key": "field_of_use",
                "name": "Field of use",
                "description": "Permitted uses.",
                "required": True,
            },
            {
                "key": "term_territory",
                "name": "Term and territory",
                "description": "Geographic and temporal scope.",
                "required": True,
            },
            {
                "key": "royalty",
                "name": "Royalty / fees",
                "description": "Compensation, if any.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Subject to the terms and conditions of this Agreement, Licensor hereby grants to "
            "Licensee a non-exclusive, non-transferable, non-sublicensable, worldwide, "
            "royalty-free license, during the Term, to use the Licensed IP solely for "
            "Licensee's internal business purposes."
        ),
        "regex_anchors": [
            r"hereby grants? (?:a|an) (?:limited|non-exclusive|exclusive|perpetual)? license",
            r"non-?exclusive license",
            r"royalty-?free license",
        ],
        "required_keywords": ["license", "grant"],
    },
    {
        "slug": "feedback_license",
        "name": "Feedback License",
        "category": "ip",
        "description": "License-back of customer feedback to provider.",
        "sub_elements": [
            {
                "key": "perpetual_irrevocable",
                "name": "Perpetual / irrevocable",
                "description": "Commonly framed as perpetual.",
                "required": True,
            },
            {
                "key": "no_obligation",
                "name": "No obligation to use",
                "description": "Provider has no duty to act on feedback.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Customer grants Provider a perpetual, irrevocable, worldwide, royalty-free, "
            "fully paid-up license to use, modify, and incorporate any feedback, suggestions, "
            "or recommendations Customer provides regarding the Services into Provider's products "
            "and services without any obligation or attribution to Customer."
        ),
        "regex_anchors": [
            r"feedback",
            r"suggestions?, (?:ideas|comments|recommendations)",
        ],
        "required_keywords": ["feedback", "license"],
    },
    # =========================================================================
    # CONFIDENTIALITY
    # =========================================================================
    {
        "slug": "confidentiality",
        "name": "Confidentiality",
        "category": "confidentiality",
        "description": "Protection of confidential information.",
        "sub_elements": [
            {
                "key": "definition",
                "name": "Definition of Confidential Information",
                "description": "What is/isn't confidential.",
                "required": True,
            },
            {
                "key": "exclusions",
                "name": "Standard exclusions",
                "description": "Public, independently developed, lawfully received, required by law.",
                "required": True,
            },
            {
                "key": "term_of_protection",
                "name": "Duration of confidentiality obligation",
                "description": "Often N years post-termination, or perpetual for trade secrets.",
                "required": True,
            },
            {
                "key": "permitted_disclosures",
                "name": "Compelled disclosure procedure",
                "description": "Notice + cooperation requirements.",
                "required": False,
            },
        ],
        "market_standard_text": (
            '"Confidential Information" means any non-public information disclosed by one party '
            '("Discloser") to the other ("Recipient"), whether orally or in writing, that is '
            "designated as confidential or that reasonably should be understood to be "
            "confidential given the nature of the information and the circumstances of disclosure. "
            "Confidential Information does not include information that: (a) is or becomes "
            "publicly available through no breach of this Agreement; (b) was known to Recipient "
            "prior to disclosure; (c) is received from a third party without restriction; or "
            "(d) is independently developed by Recipient without reference to the Confidential "
            "Information. Recipient shall protect Confidential Information using at least the "
            "same degree of care it uses to protect its own confidential information of like "
            "kind, but no less than reasonable care, for a period of three (3) years following "
            "disclosure (or, for trade secrets, for so long as such information remains a trade "
            "secret under applicable law). If compelled by law to disclose, Recipient shall give "
            "Discloser prompt notice and reasonable cooperation, at Discloser's expense, in "
            "seeking a protective order."
        ),
        "regex_anchors": [
            r"confidential information",
            r"non-?disclosure",
            r"shall (?:not |not\s+)?(?:use|disclose) (?:the |any )?confidential",
        ],
        "required_keywords": ["confidential"],
    },
    # =========================================================================
    # TERM / TERMINATION
    # =========================================================================
    {
        "slug": "term",
        "name": "Term",
        "category": "term",
        "description": "Initial and renewal term of the agreement.",
        "sub_elements": [
            {
                "key": "initial_term",
                "name": "Initial term",
                "description": "Starting period.",
                "required": True,
            },
            {
                "key": "renewal",
                "name": "Renewal mechanism",
                "description": "Auto-renew vs. mutual renewal vs. fixed.",
                "required": True,
            },
            {
                "key": "non_renewal_notice",
                "name": "Non-renewal notice period",
                "description": "Notice required to prevent renewal.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "This Agreement shall commence on the Effective Date and continue for an initial "
            'term of one (1) year (the "Initial Term"). Thereafter, this Agreement will '
            'automatically renew for successive one (1) year terms (each, a "Renewal Term") '
            "unless either party gives the other written notice of non-renewal at least thirty "
            "(30) days prior to the end of the then-current term."
        ),
        "regex_anchors": [
            r"initial term",
            r"automatically renew",
            r"renewal term",
        ],
        "required_keywords": ["term"],
    },
    {
        "slug": "termination_for_convenience",
        "name": "Termination for Convenience",
        "category": "term",
        "description": "Right to terminate without cause.",
        "sub_elements": [
            {
                "key": "notice_period",
                "name": "Notice period",
                "description": "Days of advance notice.",
                "required": True,
            },
            {
                "key": "mutual",
                "name": "Mutual",
                "description": "Both parties or only one.",
                "required": False,
            },
            {
                "key": "fee",
                "name": "Termination fee",
                "description": "Wind-down or termination charge.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Either party may terminate this Agreement, in whole or in part, for convenience "
            "by providing the other party with at least thirty (30) days' prior written notice."
        ),
        "regex_anchors": [
            r"termin(?:ate|ation) for convenience",
            r"termin(?:ate|ation) without cause",
        ],
        "required_keywords": ["terminat", "convenience"],
    },
    {
        "slug": "termination_for_cause",
        "name": "Termination for Cause",
        "category": "term",
        "description": "Termination on material breach with cure period.",
        "sub_elements": [
            {
                "key": "material_breach",
                "name": "Material breach trigger",
                "description": "Express material-breach hook.",
                "required": True,
            },
            {
                "key": "cure_period",
                "name": "Cure period",
                "description": "Days to cure after written notice.",
                "required": True,
            },
            {
                "key": "insolvency",
                "name": "Insolvency / bankruptcy trigger",
                "description": "Immediate termination on insolvency.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Either party may terminate this Agreement upon written notice if the other party "
            "(a) materially breaches this Agreement and fails to cure such breach within thirty "
            "(30) days after receiving written notice describing the breach in reasonable detail, "
            "or (b) becomes insolvent, makes a general assignment for the benefit of creditors, "
            "files or has filed against it a petition in bankruptcy, or has a receiver appointed."
        ),
        "regex_anchors": [
            r"material(?:ly)? breach",
            r"cure period",
            r"fails to cure",
        ],
        "required_keywords": ["breach", "cure"],
    },
    {
        "slug": "effects_of_termination",
        "name": "Effects of Termination",
        "category": "term",
        "description": "Survival, return/destruction, refunds.",
        "sub_elements": [
            {
                "key": "survival",
                "name": "Survival of specified clauses",
                "description": "Clauses that survive expiration.",
                "required": True,
            },
            {
                "key": "return_or_destroy",
                "name": "Return / destroy confidential info",
                "description": "Mechanism + certification.",
                "required": True,
            },
            {
                "key": "refund",
                "name": "Refund of prepaid fees",
                "description": "Whether prepaid amounts are refunded on termination by customer for cause.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Upon termination or expiration of this Agreement: (a) all rights and licenses "
            "granted hereunder shall immediately terminate; (b) each party shall promptly return "
            "or destroy the other party's Confidential Information and certify such destruction "
            "in writing upon request; and (c) the following sections shall survive: "
            "Confidentiality, Indemnification, Limitation of Liability, and Governing Law. "
            "If Customer terminates for Provider's uncured material breach, Provider shall "
            "refund any prepaid, unused fees on a pro-rata basis."
        ),
        "regex_anchors": [
            r"effect(?:s)? of termination",
            r"shall survive (?:the )?(?:termination|expiration)",
            r"return or destroy",
        ],
        "required_keywords": ["termination", "survive"],
    },
    # =========================================================================
    # PAYMENT
    # =========================================================================
    {
        "slug": "payment_terms",
        "name": "Payment Terms",
        "category": "payment",
        "description": "Invoicing, due dates, late fees, taxes.",
        "sub_elements": [
            {
                "key": "due_period",
                "name": "Net days due",
                "description": "Common: net 30.",
                "required": True,
            },
            {
                "key": "late_fee",
                "name": "Late fee / interest",
                "description": "Stated rate or 'lesser of' clause.",
                "required": False,
            },
            {
                "key": "taxes",
                "name": "Taxes allocation",
                "description": "Customer typically responsible for sales/use tax.",
                "required": True,
            },
            {
                "key": "disputes",
                "name": "Disputed invoice procedure",
                "description": "Notice + good-faith dispute window.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Customer shall pay all undisputed amounts within thirty (30) days of receipt of "
            "invoice. Late payments shall accrue interest at the lesser of 1.5% per month or "
            "the maximum rate permitted by law. All fees are exclusive of taxes, and Customer "
            "is responsible for all applicable sales, use, and similar taxes (excluding taxes "
            "on Provider's income). Customer must give written notice of any disputed amount "
            "within fifteen (15) days of the invoice date and the parties shall work in good "
            "faith to resolve the dispute."
        ),
        "regex_anchors": [
            r"net (?:thirty|30) days?",
            r"payment terms",
            r"late (?:fee|payment)",
            r"interest (?:at|of) [\d.]+%",
        ],
        "required_keywords": ["pay", "invoice"],
    },
    {
        "slug": "price_increase",
        "name": "Price Increase / Adjustment",
        "category": "payment",
        "description": "Pricing change rights at renewal.",
        "sub_elements": [
            {
                "key": "cap",
                "name": "Cap on increase",
                "description": "Often CPI or fixed % cap.",
                "required": True,
            },
            {
                "key": "notice",
                "name": "Notice period",
                "description": "Advance notice before increase takes effect.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "Provider may increase fees at the start of any Renewal Term by no more than the "
            "greater of (a) five percent (5%) or (b) the percentage increase in the U.S. "
            "Consumer Price Index (All Urban Consumers) for the prior twelve-month period, "
            "provided that Provider gives Customer at least sixty (60) days' prior written "
            "notice of any such increase."
        ),
        "regex_anchors": [
            r"price increase",
            r"fee(?:s)? (?:may|will) (?:be )?increase",
            r"CPI|consumer price index",
        ],
        "required_keywords": ["price", "increase"],
    },
    # =========================================================================
    # DATA / SECURITY / PRIVACY
    # =========================================================================
    {
        "slug": "data_security",
        "name": "Data Security",
        "category": "data",
        "description": "Information security obligations.",
        "sub_elements": [
            {
                "key": "standards",
                "name": "Security standards reference",
                "description": "ISO 27001 / SOC 2 / NIST referenced.",
                "required": True,
            },
            {
                "key": "encryption",
                "name": "Encryption in transit and at rest",
                "description": "Express encryption obligation.",
                "required": True,
            },
            {
                "key": "incident_notification",
                "name": "Security incident notification",
                "description": "Notification SLA.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "Provider shall maintain a written information security program containing "
            "administrative, technical, and physical safeguards consistent with industry "
            "standards (such as ISO/IEC 27001 or SOC 2 Type II). Provider shall encrypt all "
            "Customer Data in transit using TLS 1.2 or higher and at rest using AES-256 or an "
            "equivalent standard. Provider shall notify Customer in writing without undue delay, "
            "and in no event later than seventy-two (72) hours, after becoming aware of any "
            "unauthorized access to or disclosure of Customer Data."
        ),
        "regex_anchors": [
            r"information security",
            r"SOC 2",
            r"ISO[\s/-]?27001",
            r"data breach",
            r"security incident",
        ],
        "required_keywords": ["security", "data"],
    },
    {
        "slug": "privacy_dpa",
        "name": "Privacy / DPA Reference",
        "category": "data",
        "description": "Data processing agreement / privacy obligations.",
        "sub_elements": [
            {
                "key": "dpa_incorporated",
                "name": "DPA incorporated",
                "description": "Express DPA reference.",
                "required": True,
            },
            {
                "key": "scc_reference",
                "name": "SCCs / cross-border mechanism",
                "description": "EU/UK/Swiss SCCs or equivalent.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "To the extent Provider Processes Personal Data on behalf of Customer, the parties' "
            'Data Processing Addendum, available at [URL] ("DPA"), is incorporated by reference '
            "and forms part of this Agreement. Where transfers of Personal Data from the EEA, "
            "UK, or Switzerland to a third country are involved, the EU Standard Contractual "
            "Clauses (Module Two) and any applicable UK/Swiss addenda are incorporated and "
            "shall apply."
        ),
        "regex_anchors": [
            r"data processing (?:addendum|agreement)",
            r"\bDPA\b",
            r"standard contractual clauses",
            r"GDPR",
        ],
        "required_keywords": ["data", "process"],
    },
    # =========================================================================
    # DISPUTE RESOLUTION
    # =========================================================================
    {
        "slug": "governing_law",
        "name": "Governing Law",
        "category": "dispute",
        "description": "Choice of law.",
        "sub_elements": [
            {
                "key": "jurisdiction_named",
                "name": "Named governing jurisdiction",
                "description": "State or country.",
                "required": True,
            },
            {
                "key": "conflict_of_laws_excluded",
                "name": "Conflict-of-laws principles excluded",
                "description": "'without regard to its conflict of laws principles'.",
                "required": False,
            },
            {
                "key": "uncisg_excluded",
                "name": "UN CISG excluded",
                "description": "International sale of goods exclusion.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "This Agreement shall be governed by and construed in accordance with the laws of "
            "the State of Delaware, without regard to its conflict of laws principles. The "
            "United Nations Convention on Contracts for the International Sale of Goods does "
            "not apply."
        ),
        "regex_anchors": [
            r"governed by (?:and construed )?(?:in accordance with )?the laws? of",
            r"governing law",
            r"choice of law",
        ],
        "required_keywords": ["govern", "law"],
    },
    {
        "slug": "venue_jurisdiction",
        "name": "Venue / Forum Selection",
        "category": "dispute",
        "description": "Exclusive forum for disputes.",
        "sub_elements": [
            {
                "key": "exclusive",
                "name": "Exclusive vs. non-exclusive",
                "description": "Type of forum-selection.",
                "required": True,
            },
            {
                "key": "specific_courts",
                "name": "Specific courts named",
                "description": "State and federal courts in named county.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "Each party irrevocably consents to the exclusive jurisdiction of, and venue in, "
            "the state and federal courts located in New Castle County, Delaware, for any "
            "action arising out of or relating to this Agreement, and waives any objection "
            "based on inconvenient forum."
        ),
        "regex_anchors": [
            r"exclusive jurisdiction",
            r"venue (?:shall|will) (?:be|lie)",
            r"submit to the (?:exclusive )?jurisdiction",
        ],
        "required_keywords": ["jurisdiction"],
    },
    {
        "slug": "arbitration",
        "name": "Arbitration",
        "category": "dispute",
        "description": "Binding arbitration of disputes.",
        "sub_elements": [
            {
                "key": "rules_administrator",
                "name": "Arbitration rules + administrator",
                "description": "AAA, JAMS, ICC, etc.",
                "required": True,
            },
            {
                "key": "seat",
                "name": "Seat / location",
                "description": "Geographic seat of arbitration.",
                "required": True,
            },
            {
                "key": "language",
                "name": "Language",
                "description": "Often English.",
                "required": False,
            },
            {
                "key": "class_waiver",
                "name": "Class action waiver",
                "description": "Bars class arbitration.",
                "required": False,
            },
            {
                "key": "ip_carveout",
                "name": "IP / equitable relief carveout",
                "description": "Court relief for IP and injunctions preserved.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Any dispute arising out of or relating to this Agreement that the parties cannot "
            "resolve through good-faith negotiation within thirty (30) days shall be finally "
            "resolved by binding arbitration administered by JAMS pursuant to its Comprehensive "
            "Arbitration Rules, by a single arbitrator. The seat of arbitration shall be New "
            "York, New York, and the language of the arbitration shall be English. Each party "
            "waives any right to participate in a class, collective, or representative action. "
            "Notwithstanding the foregoing, either party may seek injunctive or other equitable "
            "relief in any court of competent jurisdiction to protect its intellectual property "
            "or confidential information."
        ),
        "regex_anchors": [
            r"binding arbitration",
            r"\bJAMS\b",
            r"\bAAA\b|American Arbitration Association",
            r"class[\s-]?action waiver",
        ],
        "required_keywords": ["arbitration"],
    },
    {
        "slug": "jury_waiver",
        "name": "Jury Trial Waiver",
        "category": "dispute",
        "description": "Mutual waiver of jury trial.",
        "sub_elements": [
            {
                "key": "mutual",
                "name": "Mutual waiver",
                "description": "Both parties waive.",
                "required": True,
            },
            {
                "key": "conspicuous",
                "name": "Conspicuous (capitalized)",
                "description": "Often required for enforceability.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "EACH PARTY HEREBY IRREVOCABLY WAIVES ANY RIGHT TO TRIAL BY JURY IN ANY ACTION OR "
            "PROCEEDING ARISING OUT OF OR RELATING TO THIS AGREEMENT."
        ),
        "regex_anchors": [
            r"waive(?:s|d)?\s+(?:the )?right to (?:a )?(?:trial by )?jury",
            r"jury trial waiver",
            r"WAIVES TRIAL BY JURY",
        ],
        "required_keywords": ["jury", "waive"],
    },
    # =========================================================================
    # RESTRICTIVE COVENANTS
    # =========================================================================
    {
        "slug": "non_compete",
        "name": "Non-Compete",
        "category": "restrictive",
        "description": "Restriction on competing during/after term.",
        "sub_elements": [
            {
                "key": "duration",
                "name": "Duration",
                "description": "Months or years post-termination.",
                "required": True,
            },
            {
                "key": "geography",
                "name": "Geographic scope",
                "description": "Defined territory.",
                "required": True,
            },
            {
                "key": "scope_of_activity",
                "name": "Scope of restricted activity",
                "description": "Tied to specific business.",
                "required": True,
            },
            {
                "key": "consideration",
                "name": "Independent consideration",
                "description": "Required in some states (e.g., NC, TX).",
                "required": False,
            },
        ],
        "market_standard_text": (
            "During the term of this Agreement and for twelve (12) months thereafter, "
            "Recipient shall not, directly or indirectly, within the United States, engage in "
            "any business that competes with the specific products or services Recipient had "
            "material involvement with under this Agreement."
        ),
        "regex_anchors": [
            r"non[\s-]?compete",
            r"shall not (?:directly or indirectly )?(?:compete|engage in)",
            r"covenant not to compete",
        ],
        "required_keywords": ["compete"],
    },
    {
        "slug": "non_solicit",
        "name": "Non-Solicitation",
        "category": "restrictive",
        "description": "Restriction on soliciting employees / customers.",
        "sub_elements": [
            {
                "key": "duration",
                "name": "Duration",
                "description": "Period post-termination.",
                "required": True,
            },
            {
                "key": "scope_targets",
                "name": "Targets",
                "description": "Employees, customers, or both.",
                "required": True,
            },
            {
                "key": "general_advertising_carveout",
                "name": "General advertising carveout",
                "description": "Exclusion for general public hiring efforts.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "During the term of this Agreement and for twelve (12) months thereafter, neither "
            "party shall, directly or indirectly, solicit for employment any employee of the "
            "other party with whom it had material contact in connection with this Agreement; "
            "provided that general advertising not directed at such employees shall not be a "
            "violation of this Section."
        ),
        "regex_anchors": [
            r"non[\s-]?solicit(?:ation)?",
            r"shall not (?:directly or indirectly )?solicit",
            r"hire,?\s+solicit",
        ],
        "required_keywords": ["solicit"],
    },
    # =========================================================================
    # ASSIGNMENT / CHANGE OF CONTROL
    # =========================================================================
    {
        "slug": "assignment",
        "name": "Assignment",
        "category": "general",
        "description": "Restrictions on assigning the agreement.",
        "sub_elements": [
            {
                "key": "consent_required",
                "name": "Consent required",
                "description": "Default: written consent required.",
                "required": True,
            },
            {
                "key": "affiliate_carveout",
                "name": "Affiliate / change-of-control carveout",
                "description": "Permitted assignments to affiliates / acquirers.",
                "required": False,
            },
            {
                "key": "void_if_violated",
                "name": "Void if violated",
                "description": "Express void clause.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Neither party may assign or transfer this Agreement, in whole or in part, without "
            "the other party's prior written consent, except that either party may assign this "
            "Agreement, upon written notice and without consent, to an affiliate or in "
            "connection with a merger, acquisition, corporate reorganization, or sale of all or "
            "substantially all of its assets. Any purported assignment in violation of this "
            "Section is void."
        ),
        "regex_anchors": [
            r"assign(?:ment|s)?",
            r"prior written consent",
            r"merger,? acquisition",
        ],
        "required_keywords": ["assign", "consent"],
    },
    # =========================================================================
    # GENERAL / MISC
    # =========================================================================
    {
        "slug": "force_majeure",
        "name": "Force Majeure",
        "category": "general",
        "description": "Excuse for performance during specified events.",
        "sub_elements": [
            {
                "key": "covered_events",
                "name": "Covered events",
                "description": "Acts of God, war, pandemic, etc.",
                "required": True,
            },
            {
                "key": "payment_carveout",
                "name": "Payment-obligation carveout",
                "description": "Payment is generally not excused.",
                "required": True,
            },
            {
                "key": "termination_after_extended_event",
                "name": "Termination right after extended event",
                "description": "After N days of continued event.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Neither party shall be liable for any failure or delay in performance under this "
            "Agreement (other than payment obligations) due to causes beyond its reasonable "
            "control, including acts of God, war, terrorism, civil disturbance, pandemic, "
            "governmental order, or failure of public utilities or the Internet. The affected "
            "party shall give prompt notice and use reasonable efforts to resume performance. "
            "If a force majeure event continues for more than thirty (30) days, the non-affected "
            "party may terminate this Agreement upon written notice."
        ),
        "regex_anchors": [
            r"force majeure",
            r"acts? of god",
            r"beyond (?:its|such party'?s) reasonable control",
        ],
        "required_keywords": ["force majeure"],
    },
    {
        "slug": "entire_agreement",
        "name": "Entire Agreement / Integration",
        "category": "general",
        "description": "Merger clause.",
        "sub_elements": [
            {
                "key": "integration",
                "name": "Integration statement",
                "description": "Supersedes prior agreements.",
                "required": True,
            },
            {
                "key": "no_oral_modification",
                "name": "No oral modification",
                "description": "Amendments require writing.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "This Agreement constitutes the entire agreement between the parties regarding its "
            "subject matter and supersedes all prior or contemporaneous agreements, "
            "understandings, and communications, whether written or oral. No modification or "
            "amendment to this Agreement is binding unless in a writing signed by an authorized "
            "representative of each party."
        ),
        "regex_anchors": [
            r"entire agreement",
            r"supersedes? all prior",
            r"no (?:oral )?modification",
        ],
        "required_keywords": ["entire", "agreement"],
    },
    {
        "slug": "severability",
        "name": "Severability",
        "category": "general",
        "description": "Invalidation of one provision does not invalidate the rest.",
        "sub_elements": [
            {
                "key": "blue_pencil",
                "name": "Reformation / blue pencil",
                "description": "Court may reform.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "If any provision of this Agreement is held to be invalid, illegal, or "
            "unenforceable, that provision shall be modified to the minimum extent necessary to "
            "make it enforceable, and the remaining provisions shall remain in full force and "
            "effect."
        ),
        "regex_anchors": [
            r"severability",
            r"unenforceable",
            r"invalid,?\s+illegal,?\s+or unenforceable",
        ],
        "required_keywords": ["severab", "unenforceable"],
    },
    {
        "slug": "notices",
        "name": "Notices",
        "category": "general",
        "description": "How and where notices are sent.",
        "sub_elements": [
            {
                "key": "addresses",
                "name": "Addresses specified",
                "description": "Notice addresses.",
                "required": True,
            },
            {
                "key": "methods",
                "name": "Permitted methods",
                "description": "Mail, email, courier.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "All notices under this Agreement must be in writing and shall be deemed given "
            "(a) upon receipt when delivered personally or by nationally recognized overnight "
            "courier, (b) on the third business day after deposit with the U.S. Postal Service, "
            "certified mail, return receipt requested, or (c) on confirmation of receipt when "
            "sent by email to the addresses specified on the signature page or such other "
            "address as a party may designate by notice."
        ),
        "regex_anchors": [
            r"\bnotices?\b",
            r"deemed (?:given|received)",
            r"certified mail",
        ],
        "required_keywords": ["notice"],
    },
    {
        "slug": "audit_rights",
        "name": "Audit Rights",
        "category": "general",
        "description": "Right to audit compliance / records.",
        "sub_elements": [
            {
                "key": "frequency",
                "name": "Frequency limit",
                "description": "Often once per twelve months.",
                "required": True,
            },
            {
                "key": "notice_period",
                "name": "Notice period",
                "description": "Advance notice.",
                "required": True,
            },
            {
                "key": "cost_allocation",
                "name": "Cost allocation",
                "description": "Auditor pays unless material discrepancy.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Upon at least thirty (30) days' prior written notice, but not more than once per "
            "twelve-month period (except for cause), Customer or its independent auditor may, "
            "during normal business hours and subject to reasonable confidentiality obligations, "
            "audit Provider's books and records solely to verify compliance with this Agreement. "
            "Customer shall bear the cost of the audit unless it reveals an underpayment or "
            "material non-compliance, in which case Provider shall reimburse the reasonable "
            "audit costs."
        ),
        "regex_anchors": [
            r"audit rights?",
            r"audit (?:provider|customer|its)",
            r"books and records",
        ],
        "required_keywords": ["audit"],
    },
    {
        "slug": "publicity",
        "name": "Publicity",
        "category": "general",
        "description": "Use of name / logo / case studies.",
        "sub_elements": [
            {
                "key": "consent_required",
                "name": "Consent required",
                "description": "Written consent before any publicity.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "Neither party shall issue any press release or public statement, or use the other "
            "party's name, trademarks, or logos, without the other party's prior written consent."
        ),
        "regex_anchors": [
            r"publicity",
            r"press release",
            r"name,?\s+(?:logo|trademark)",
        ],
        "required_keywords": ["publicity"],
    },
    {
        "slug": "insurance",
        "name": "Insurance",
        "category": "general",
        "description": "Required insurance coverage.",
        "sub_elements": [
            {
                "key": "types",
                "name": "Types of coverage",
                "description": "CGL, E&O, cyber, workers comp, etc.",
                "required": True,
            },
            {
                "key": "minimums",
                "name": "Coverage minimums",
                "description": "Per-occurrence and aggregate.",
                "required": True,
            },
            {
                "key": "additional_insured",
                "name": "Additional insured / certificate",
                "description": "Endorsement requirement.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Provider shall maintain, at its sole cost, the following insurance during the term: "
            "(a) Commercial General Liability with limits of at least $1,000,000 per occurrence "
            "and $2,000,000 aggregate; (b) Professional Liability / Errors & Omissions of at "
            "least $2,000,000 per claim; (c) Cyber / Technology E&O of at least $5,000,000 per "
            "claim; and (d) Workers' Compensation as required by law. Provider shall name "
            "Customer as additional insured (other than for workers' compensation and "
            "professional liability) and provide certificates of insurance upon request."
        ),
        "regex_anchors": [
            r"\binsurance\b",
            r"commercial general liability",
            r"errors and omissions",
        ],
        "required_keywords": ["insurance"],
    },
    {
        "slug": "export_controls",
        "name": "Export Controls / Sanctions",
        "category": "compliance",
        "description": "Compliance with trade controls.",
        "sub_elements": [
            {
                "key": "us_export_compliance",
                "name": "U.S. export law compliance",
                "description": "EAR / OFAC reference.",
                "required": True,
            },
            {
                "key": "embargo_certification",
                "name": "Embargoed-country certification",
                "description": "Customer certifies it is not in a sanctioned country.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "Each party shall comply with all applicable export control and sanctions laws and "
            "regulations, including the U.S. Export Administration Regulations and the "
            "regulations administered by the U.S. Department of the Treasury's Office of "
            "Foreign Assets Control. Customer represents that it is not located in, organized "
            "under the laws of, or ordinarily resident in any country or region subject to "
            "comprehensive U.S. sanctions, and is not on any U.S. restricted-party list."
        ),
        "regex_anchors": [
            r"export (?:control|administration)",
            r"\bOFAC\b",
            r"sanctions? laws?",
        ],
        "required_keywords": ["export"],
    },
    {
        "slug": "anti_corruption",
        "name": "Anti-Corruption",
        "category": "compliance",
        "description": "FCPA / anti-bribery compliance.",
        "sub_elements": [
            {
                "key": "fcpa_compliance",
                "name": "FCPA / UK Bribery Act compliance",
                "description": "Express compliance with anti-bribery laws.",
                "required": True,
            },
        ],
        "market_standard_text": (
            "Each party shall comply with all applicable anti-corruption laws, including the "
            "U.S. Foreign Corrupt Practices Act and the U.K. Bribery Act, and shall not, "
            "directly or indirectly, offer, promise, or give anything of value to any "
            "government official or other person to improperly influence any act or decision."
        ),
        "regex_anchors": [
            r"anti[\s-]?corruption",
            r"\bFCPA\b",
            r"foreign corrupt practices act",
            r"bribery",
        ],
        "required_keywords": ["corrupt"],
    },
    {
        "slug": "counterparts",
        "name": "Counterparts",
        "category": "general",
        "description": "Execution in counterparts; e-signatures.",
        "sub_elements": [
            {
                "key": "esign_recognized",
                "name": "Electronic signatures",
                "description": "DocuSign / e-signature recognition.",
                "required": False,
            },
        ],
        "market_standard_text": (
            "This Agreement may be executed in any number of counterparts, each of which shall "
            "be deemed an original, and all of which together shall constitute one and the "
            "same instrument. Signatures delivered by electronic means (including DocuSign or "
            "similar services) shall have the same legal effect as original signatures."
        ),
        "regex_anchors": [
            r"counterparts",
            r"electronic signature",
            r"DocuSign",
        ],
        "required_keywords": ["counterpart"],
    },
]


# =============================================================================
# Contract type → required / recommended canonical clauses
# =============================================================================

CONTRACT_TYPE_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "nda": {
        "required": [
            "confidentiality",
            "term",
            "effects_of_termination",
            "governing_law",
            "venue_jurisdiction",
            "entire_agreement",
            "notices",
        ],
        "recommended": [
            "non_solicit",
            "feedback_license",
            "severability",
            "counterparts",
        ],
    },
    "msa": {
        "required": [
            "confidentiality",
            "indemnification",
            "limitation_of_liability",
            "warranty_disclaimer",
            "ip_assignment",
            "term",
            "termination_for_cause",
            "termination_for_convenience",
            "effects_of_termination",
            "payment_terms",
            "governing_law",
            "venue_jurisdiction",
            "assignment",
            "entire_agreement",
            "notices",
            "force_majeure",
            "severability",
        ],
        "recommended": [
            "data_security",
            "privacy_dpa",
            "audit_rights",
            "insurance",
            "publicity",
            "anti_corruption",
            "export_controls",
            "counterparts",
            "feedback_license",
        ],
    },
    "saas": {
        "required": [
            "confidentiality",
            "indemnification",
            "limitation_of_liability",
            "warranty_disclaimer",
            "ip_license",
            "term",
            "termination_for_cause",
            "effects_of_termination",
            "payment_terms",
            "data_security",
            "privacy_dpa",
            "governing_law",
            "venue_jurisdiction",
            "assignment",
            "entire_agreement",
            "notices",
            "force_majeure",
            "severability",
        ],
        "recommended": [
            "termination_for_convenience",
            "price_increase",
            "audit_rights",
            "feedback_license",
            "publicity",
            "insurance",
            "counterparts",
        ],
    },
    "employment": {
        "required": [
            "confidentiality",
            "ip_assignment",
            "term",
            "termination_for_cause",
            "termination_for_convenience",
            "governing_law",
            "venue_jurisdiction",
            "entire_agreement",
            "notices",
        ],
        "recommended": [
            "non_compete",
            "non_solicit",
            "arbitration",
            "jury_waiver",
            "severability",
        ],
    },
    "license": {
        "required": [
            "ip_license",
            "confidentiality",
            "indemnification",
            "limitation_of_liability",
            "warranty_disclaimer",
            "term",
            "termination_for_cause",
            "effects_of_termination",
            "payment_terms",
            "governing_law",
            "venue_jurisdiction",
            "assignment",
            "entire_agreement",
        ],
        "recommended": [
            "audit_rights",
            "force_majeure",
            "severability",
            "notices",
            "counterparts",
        ],
    },
    "sow": {
        "required": [
            "ip_assignment",
            "payment_terms",
            "term",
            "termination_for_cause",
            "governing_law",
            "entire_agreement",
        ],
        "recommended": [
            "limitation_of_liability",
            "warranty_disclaimer",
            "indemnification",
            "notices",
        ],
    },
}


def get_canonical_by_slug(slug: str) -> dict | None:
    for c in CANONICAL_CLAUSES:
        if c["slug"] == slug:
            return c
    return None
