"""
Party graph resolver.

Resolves party aliases ('Provider', 'Licensor', 'the Company', 'ABC Inc.')
to a canonical party with role + observed surface forms.

Pipeline:
  1. Find defined-party patterns: '<Name> ("<Alias>")' in the preamble
  2. Find recital "by and between A and B" patterns
  3. Detect generic-role tokens (Provider, Customer, Licensor, Licensee, etc.)
  4. Resolve overlapping aliases (same alias across multiple definitions wins)

Output is a list of canonical parties; each obligation extractor downstream
references parties by canonical name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ResolvedParty:
    canonical_name: str
    role: str | None = None
    aliases: list[str] = field(default_factory=list)
    first_span_start: int | None = None
    first_span_end: int | None = None
    detection_method: str = "heuristic"
    confidence: float = 1.0


# Match: 'ABC Corporation, a Delaware corporation ("ABC")' or '"Provider"'
# The entity is the last noun-phrase chunk before the alias parens — limit to
# at most 6 capitalized words plus optional comma-clause, no leading articles
# or boilerplate connectors.
_DEFINED_PARTY_RE = re.compile(
    r"(?<![\w])"
    r"(?P<entity>"
    r"(?:[A-Z][A-Za-z0-9.\-&/]+\s*){1,6}"  # entity nucleus
    r"(?:,\s+(?:a|an)\s+[A-Za-z][A-Za-z &\-]{2,60}\s+(?:corporation|company|LLC|L\.L\.C\.|Inc\.?|partnership|LP|LLP|trust|foundation|association|individual))?"
    r")"
    r'\s*\(\s*[\'"](?P<alias>[A-Z][A-Za-z &\-]{1,40})[\'"]\s*\)'
)

# Stop phrases — entity capture should not include these
_BAD_ENTITY_PREFIX_RE = re.compile(
    r"^\s*(?:by\s+and\s+between\s+|between\s+|This\s+|the\s+)",
    re.IGNORECASE,
)

# Match: "by and between Foo Inc. ('Foo') and Bar LLC ('Bar')"
_BETWEEN_RE = re.compile(
    r"by\s+and\s+between\s+(?P<a>[A-Z][A-Za-z0-9 ,&\-./]{2,120})\s+and\s+(?P<b>[A-Z][A-Za-z0-9 ,&\-./]{2,120})",
    re.IGNORECASE,
)

# Generic role tokens that appear without a definition
_GENERIC_ROLES = [
    "Provider",
    "Customer",
    "Client",
    "Licensor",
    "Licensee",
    "Buyer",
    "Seller",
    "Disclosing Party",
    "Receiving Party",
    "Discloser",
    "Recipient",
    "Indemnitor",
    "Indemnitee",
    "Company",
    "Employee",
    "Contractor",
    "Vendor",
    "Supplier",
    "Lessor",
    "Lessee",
    "Landlord",
    "Tenant",
]


def _role_for_alias(alias: str) -> str | None:
    a = alias.lower()
    if a in {
        "provider",
        "licensor",
        "discloser",
        "disclosing party",
        "vendor",
        "supplier",
        "lessor",
        "landlord",
        "indemnitor",
    }:
        return "provider"
    if a in {
        "customer",
        "client",
        "licensee",
        "recipient",
        "receiving party",
        "buyer",
        "lessee",
        "tenant",
        "indemnitee",
    }:
        return "customer"
    if a in {"company", "employer"}:
        return "company"
    if a in {"employee", "contractor"}:
        return "individual"
    return None


def resolve_parties(text: str, max_chars: int = 4000) -> list[ResolvedParty]:
    """
    Identify parties in the contract.

    Only inspects the first `max_chars` (preamble/recitals) which is where
    party definitions live in commercial contracts.
    """
    if not text:
        return []
    head = text[:max_chars]
    parties: dict[str, ResolvedParty] = {}

    # 1) Defined parties via parens-quote
    for m in _DEFINED_PARTY_RE.finditer(head):
        entity = m.group("entity").strip(" ,.-\n\t")
        # Strip boilerplate prefixes that the regex may have admitted
        entity = _BAD_ENTITY_PREFIX_RE.sub("", entity).strip(" ,.-")
        # If anything is left looking like a date, drop the whole match
        if re.match(r"^[A-Z][a-z]+\s+\d{1,2},\s+\d{4}", entity):
            continue
        if not entity or len(entity) < 2:
            continue
        alias = m.group("alias").strip()
        key = alias.lower()
        rp = parties.get(key)
        if rp is None:
            rp = ResolvedParty(
                canonical_name=entity,
                role=_role_for_alias(alias),
                aliases=[alias, entity],
                first_span_start=m.start(),
                first_span_end=m.end(),
                detection_method="defined",
                confidence=1.0,
            )
            parties[key] = rp
        else:
            if alias not in rp.aliases:
                rp.aliases.append(alias)
            if entity not in rp.aliases:
                rp.aliases.append(entity)

    # 2) "between A and B" — only used if no defined parties found
    if not parties:
        m = _BETWEEN_RE.search(head)
        if m:
            for grp in ("a", "b"):
                name = m.group(grp).strip(" ,.-")
                key = name.lower()
                parties[key] = ResolvedParty(
                    canonical_name=name,
                    role=None,
                    aliases=[name],
                    first_span_start=m.start(grp),
                    first_span_end=m.end(grp),
                    detection_method="header",
                    confidence=0.85,
                )

    # 3) Generic roles found anywhere in the doc
    for role_alias in _GENERIC_ROLES:
        rx = re.compile(r"\b" + re.escape(role_alias) + r"\b")
        m = rx.search(head)
        if m and role_alias.lower() not in parties:
            parties[role_alias.lower()] = ResolvedParty(
                canonical_name=role_alias,
                role=_role_for_alias(role_alias),
                aliases=[role_alias],
                first_span_start=m.start(),
                first_span_end=m.end(),
                detection_method="heuristic",
                confidence=0.6,
            )

    return list(parties.values())
