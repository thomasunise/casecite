"""Deep case-law research: read full opinions, keep only verified authority.

Shared engine behind two features:

- The strategy brief (``strategy.py``) uses the windowing / quote-verification
  helpers here for its per-point authority stage.
- Research-intent chat ("find me case law on X") calls
  :func:`research_authorities` — the question is decomposed into legal
  propositions, CourtListener candidates are read IN FULL, and only opinions
  whose supporting quote verifies verbatim against the real opinion text are
  returned, each with a one-sentence explanation of why it matters.

The hard rule everywhere: a citation the model endorses but cannot ground in
the opinion's own text is dropped, never shown.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.services.authority_mapper.service import find_quote_offset
from app.services.courtlistener import courtlistener_service
from app.services.llm_clients import openai_chat, utility_model
from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block

logger = logging.getLogger(__name__)

WINDOW_CHARS = 80_000
WINDOW_OVERLAP = 2_000
MAX_CONCEPTS = 3
CANDIDATES_PER_CONCEPT = 4
CONCURRENCY = 6


def opinion_windows(text: str) -> list[str]:
    """Split an opinion into judge windows covering the ENTIRE text.

    Windows overlap by WINDOW_OVERLAP so a holding that straddles a boundary
    still appears whole in one window. A 600-page opinion simply yields more
    windows — no part of the opinion is ever skipped.
    """
    if len(text) <= WINDOW_CHARS:
        return [text]
    windows: list[str] = []
    step = WINDOW_CHARS - WINDOW_OVERLAP
    for start in range(0, len(text), step):
        windows.append(text[start : start + WINDOW_CHARS])
        if start + WINDOW_CHARS >= len(text):
            break
    return windows


def verify_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Locate the judge's quote in the FULL opinion text.

    Models drift on punctuation across sentence boundaries; before giving up,
    try to verify the quote's longest sentence alone.
    """
    offsets = find_quote_offset(text, quote) if quote else None
    if offsets is None and quote:
        sentences = sorted(
            (part.strip() for part in re.split(r"(?<=[.;])\s+", quote)),
            key=len,
            reverse=True,
        )
        for sentence in sentences:
            if len(sentence) < 40:
                break
            offsets = find_quote_offset(text, sentence)
            if offsets:
                break
    return offsets


async def _craft_research_targets(
    client, question: str, search_query: str | None
) -> list[dict[str, str]]:
    """Decompose a research question into 1-3 doctrine propositions + queries.

    Falls back to a single target built from the question / distilled query on
    any failure — research must never die on the decomposition step.
    """
    fallback = [{"proposition": question[:400], "query": (search_query or question)[:80]}]
    try:
        prompt = (
            "A lawyer is researching case law. Break their request into the "
            "distinct legal propositions worth searching for (1 for a simple "
            f"request, up to {MAX_CONCEPTS} for a compound one).\n\n"
            'For each: (a) "proposition" — ONE sentence stating the rule of '
            "law or doctrine the research should establish (no party names); "
            '(b) "query" — 3-7 keywords naming that doctrine for a case-law '
            "keyword search.\n\n"
            f"REQUEST: {question[:1500]}\n\n"
            'Return STRICT JSON: {"targets": [{"proposition": "...", "query": "..."}, ...]}'
        )
        resp = await openai_chat(
            client,
            model=utility_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        targets = data.get("targets")
        if isinstance(targets, list) and targets:
            cleaned = [
                {
                    "proposition": str(t.get("proposition") or "").strip(),
                    "query": str(t.get("query") or "").strip(),
                }
                for t in targets[:MAX_CONCEPTS]
                if isinstance(t, dict)
            ]
            cleaned = [t for t in cleaned if t["proposition"] and t["query"]]
            if cleaned:
                return cleaned
    except Exception as e:  # decomposition is an optimization, never fatal
        logger.warning(f"Case-law research target crafting failed, using question: {e}")
    return fallback


async def _read_and_judge(
    client,
    semaphore: asyncio.Semaphore,
    question: str,
    proposition: str,
    opinion,
    rank: int,
) -> tuple[dict[str, Any] | None, str]:
    """Read one opinion IN FULL and decide whether it answers the research.

    Returns (result, reason): result is a search-result-shaped dict (the same
    shape ``search_case_law`` produces, so every downstream stage — context
    building, citation building, the unverified-reference guard — works
    unchanged) or None; reason is one of "attached", "unreadable",
    "unsupportive", "quote_unverified", "error". Never raises.
    """
    try:
        full = await courtlistener_service.get_opinion(opinion.id)
    except Exception as e:  # per-candidate, never fails the research
        logger.warning(f"Case-law research opinion fetch failed ({opinion.id}): {e}")
        return None, "unreadable"
    text = (getattr(full, "text", None) or "") if full else ""
    if not text.strip():
        return None, "unreadable"

    citation_str = opinion.citation[0] if opinion.citation else "No citation"
    windows = opinion_windows(text)
    endorsed_but_unverified = False
    for index, window in enumerate(windows):
        prompt = (
            "You are selecting legal authority for a lawyer's research request.\n\n"
            f"RESEARCH REQUEST: {question[:600]}\n\n"
            f"PROPOSITION BEING RESEARCHED: {proposition[:400]}\n\n"
            f"CASE: {opinion.case_name}"
            f"{' (' + citation_str + ')' if opinion.citation else ''}\n"
            f"{UNTRUSTED_CONTENT_RULE}\n\n"
            f"OPINION TEXT (part {index + 1} of {len(windows)}):\n"
            f"{untrusted_block(f'Opinion text, part {index + 1} of {len(windows)}', window)}\n\n"
            "Does this part of the opinion state a rule of law, holding, or "
            "reasoning that genuinely bears on the proposition — something a "
            "lawyer doing this research would want to read? Off-topic "
            "keyword matches do not count.\n\n"
            'Return STRICT JSON: {"relevant": true|false, '
            '"quote": "ONE contiguous passage of 1-3 sentences copied EXACTLY, '
            "character for character, from the opinion text above, stating the "
            'relevant rule or holding — or empty", '
            '"why": "one sentence on why this case matters for the research '
            'request, or empty"}'
        )
        try:
            async with semaphore:
                resp = await openai_chat(
                    client,
                    model=utility_model(),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:  # per-candidate, never fails the research
            logger.warning(f"Case-law research judge call failed ({opinion.id}): {e}")
            return None, "error"
        if not (isinstance(data, dict) and data.get("relevant")):
            continue

        quote = str(data.get("quote") or "").strip()
        offsets = verify_quote(text, quote)
        if offsets is None:
            # Endorsed but ungrounded in THIS window — keep scanning: a later
            # part of the opinion may yield a verifiable quote.
            endorsed_but_unverified = True
            continue
        verified_quote = text[offsets[0] : offsets[1]]
        why = str(data.get("why") or "").strip() or None
        date_filed = getattr(opinion, "date_filed", None)

        return {
            "id": f"courtlistener_{opinion.id}",
            "text": verified_quote[:1500],
            "metadata": {
                "filename": f"{opinion.case_name} ({citation_str})",
                "source": "courtlistener",
                "doc_type": "case_law",
                "court": getattr(opinion, "court", None),
                "date_filed": str(date_filed) if date_filed else None,
                "citation": citation_str,
                "url": getattr(opinion, "absolute_url", None),
                "chunk_index": 0,
                "case_name": opinion.case_name,
                # The judge's reason this case matters — surfaced in the
                # Citations tab as the case summary.
                "case_summary": why,
                "quote_verified": True,
            },
            # The quote verified verbatim against the full opinion — this is
            # a confirmed authority, not a search-rank guess.
            "similarity": 0.9,
            "rank": rank,
        }, "attached"

    return None, "quote_unverified" if endorsed_but_unverified else "unsupportive"


async def research_authorities(
    question: str,
    search_query: str | None,
    client,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Full deep-research pass: concepts -> search -> full reads -> verified quotes.

    Returns (results, status). Results are search-result-shaped dicts (see
    ``_read_and_judge``); status carries per-reason drop counters. Never
    raises — an empty list with counters is the worst case.
    """
    status = {
        "concepts": 0,
        "opinions_read": 0,
        "attached": 0,
        "unreadable": 0,
        "unsupportive": 0,
        "quote_unverified": 0,
        "errors": 0,
        "searches_failed": 0,
    }
    targets = await _craft_research_targets(client, question, search_query)
    status["concepts"] = len(targets)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # Search all concepts, dedupe opinions across them (a case can hit
    # multiple doctrine queries; read it once, for its first concept).
    candidates: list[tuple[dict[str, str], Any]] = []
    seen_ids: set[int] = set()
    for target in targets:
        try:
            opinions = await courtlistener_service.search_opinions(
                query=target["query"], limit=CANDIDATES_PER_CONCEPT, cited_gt=2
            )
        except Exception as e:  # per-concept, other concepts continue
            logger.warning(f"Case-law research search failed ({target['query']!r}): {e}")
            status["searches_failed"] += 1
            status.setdefault("search_error", f"{type(e).__name__}: {e}"[:200])
            continue
        for opinion in (opinions or [])[:CANDIDATES_PER_CONCEPT]:
            if opinion.id in seen_ids:
                continue
            seen_ids.add(opinion.id)
            candidates.append((target, opinion))

    if not candidates:
        return [], status

    judged = await asyncio.gather(
        *(
            _read_and_judge(client, semaphore, question, target["proposition"], op, i + 1)
            for i, (target, op) in enumerate(candidates)
        )
    )
    results: list[dict[str, Any]] = []
    for result, reason in judged:
        if reason != "unreadable":
            status["opinions_read"] += 1
        if result is not None:
            results.append(result)
        elif reason == "error":
            status["errors"] += 1
        else:
            status[reason] += 1

    results = results[:limit]
    status["attached"] = len(results)
    return results, status
