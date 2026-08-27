"""
Authority Mapper service.

Reads an uploaded document, extracts the key legal propositions, retrieves
candidate authorities from CourtListener (published case law only — the user's
own corpus is deliberately NOT searched: client documents are not authority,
and the top vector match for a document is the document itself), and —
critically — verifies each supporting quote is present *verbatim* in the real
source text before presenting it. Unverifiable quotes are flagged, never
silently shown. Results are persisted with character offsets so the frontend
can anchor each citation back to its exact location for due-diligence review.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.authority_map import AuthorityMapping, AuthorityMapRun
from app.services.courtlistener import courtlistener_service
from app.services.llm_clients import make_openai, openai_chat, utility_model

logger = logging.getLogger(__name__)

# Bounds keep the (async) job's cost and latency predictable.
MAX_PROPOSITIONS = 8
MAX_CANDIDATES_PER_PROP = 4
OPINION_TEXT_LIMIT = 14000
DOC_TEXT_LIMIT = 18000


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_quote_offset(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate ``needle`` in ``haystack``, tolerant of whitespace differences.

    Returns (start, end) offsets into the ORIGINAL haystack, or None if the
    quote cannot be located. This is the verification gate: a quote that cannot
    be found (modulo whitespace) in the source is treated as unverified — the
    mechanism that catches hallucinated citations instead of shipping them.
    """
    if not haystack or not needle:
        return None
    idx = haystack.find(needle)
    if idx >= 0:
        return (idx, idx + len(needle))
    norm = _normalize_ws(needle)
    if len(norm) < 12:  # too short to verify confidently
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in norm.split(" "))
    try:
        m = re.search(pattern, haystack)
    except re.error:
        return None
    return (m.start(), m.end()) if m else None


class AuthorityMapperService:
    def _api_key(self, user_keys) -> str | None:
        if user_keys and getattr(user_keys, "openai", None):
            return user_keys.openai
        return settings.openai_api_key

    async def _extract_propositions(self, client, text: str) -> list[dict]:
        prompt = (
            "You are a litigation research assistant. Read the document and identify the "
            "key legal propositions or factual assertions that would benefit from supporting "
            "case-law authority. For each, copy the EXACT verbatim quote from the document "
            "(character-for-character, do not paraphrase) and give a short search query a "
            "lawyer would use to find supporting cases.\n\n"
            'Return STRICT JSON: {"propositions":[{"proposition":"...","doc_quote":"...verbatim...",'
            '"query":"..."}]}.\n'
            f"Return at most {MAX_PROPOSITIONS} of the most important.\n\nDOCUMENT:\n"
            + text[:DOC_TEXT_LIMIT]
        )
        resp = await openai_chat(
            client,
            model=utility_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        props = data.get("propositions") or []
        return props[:MAX_PROPOSITIONS]

    async def _check_support(
        self, client, proposition: str, source_name: str, source_text: str
    ) -> dict:
        prompt = (
            "A lawyer needs authority supporting this proposition:\n"
            f'"{proposition}"\n\n'
            f"Below is the text of {source_name}. If — and only if — it contains language that "
            "supports the proposition, copy the single most on-point passage VERBATIM "
            "(character-for-character, no paraphrase, no ellipses). If it does not support the "
            "proposition, return supports=false.\n\n"
            "When supports=true, ALSO explain your relevance determination as an explicit "
            "reasoning chain of 3-5 steps a reviewing attorney can audit. Each step has a short "
            'type label (e.g. "Proposition", "Holding", "Support", "Limitation") plus a '
            "description, and optionally the specific language relied on as evidence. Cover: "
            "what the proposition asserts; what this source actually holds or states; why that "
            "holding supports the proposition (rule, reasoning, or facts — be specific); and any "
            "caveats (different jurisdiction, dicta, distinguishable facts). Finish with a "
            "one-sentence application: how a lawyer would deploy this authority for the "
            "proposition.\n\n"
            "Return STRICT JSON: "
            '{"supports":true|false,"quote":"...verbatim...","relevance":0.0-1.0,'
            '"reasoning":[{"type":"...","description":"...","evidence":"..."}],'
            '"application":"..."}.\n\n'
            f"SOURCE:\n{source_text[:OPINION_TEXT_LIMIT]}"
        )
        resp = await openai_chat(
            client,
            model=utility_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")

    @staticmethod
    def _clean_reasoning(res: dict) -> dict | None:
        """Normalize the LLM's reasoning payload into {"steps": [...], "application": str}."""
        steps = []
        for step in res.get("reasoning") or []:
            if not isinstance(step, dict):
                continue
            description = str(step.get("description") or "").strip()
            if not description:
                continue
            steps.append(
                {
                    "type": str(step.get("type") or "Analysis").strip()[:40],
                    "description": description,
                    "evidence": (str(step.get("evidence")).strip() or None)
                    if step.get("evidence")
                    else None,
                }
            )
        application = str(res.get("application") or "").strip() or None
        if not steps and not application:
            return None
        return {"steps": steps, "application": application}

    async def _courtlistener_candidates(self, query: str, jurisdiction: str | None) -> list[tuple]:
        candidates: list[tuple] = []
        try:
            opinions = await courtlistener_service.search_by_topic(
                query, jurisdiction=jurisdiction, limit=MAX_CANDIDATES_PER_PROP
            )
        except Exception as e:
            logger.warning(f"CourtListener search failed: {e}")
            return candidates
        for op in opinions[:MAX_CANDIDATES_PER_PROP]:
            text = op.text or ""
            if not text:
                try:
                    full = await courtlistener_service.get_opinion(op.id)
                    text = (full.text if full else "") or ""
                except Exception:
                    text = ""
            if not text:
                continue
            cite = op.citation[0] if op.citation else None
            candidates.append(
                ("courtlistener", op.case_name, cite, str(op.id), op.absolute_url, text)
            )
        return candidates

    async def analyze(
        self,
        *,
        text: str,
        document_name: str | None,
        document_id: str | None,
        jurisdiction: str | None,
        user_id: str,
        user_keys=None,
    ) -> dict:
        client = make_openai(self._api_key(user_keys), async_=True)
        if client is None:
            raise ValueError(
                "An OpenAI API key or a custom LLM endpoint is required. Configure one in Settings."
            )
        run_id = uuid.uuid4().hex

        props = await self._extract_propositions(client, text)
        mappings: list[dict] = []

        for p in props:
            proposition = (p.get("proposition") or "").strip()
            if not proposition:
                continue
            doc_quote = (p.get("doc_quote") or "").strip()
            query = (p.get("query") or proposition).strip()
            doc_off = find_quote_offset(text, doc_quote) if doc_quote else None

            candidates = await self._courtlistener_candidates(query, jurisdiction)

            for source, case_name, cite, source_ref, source_url, ctext in candidates:
                try:
                    res = await self._check_support(
                        client, proposition, case_name or "this source", ctext
                    )
                except Exception as e:
                    logger.warning(f"support check failed: {e}")
                    continue
                if not res.get("supports"):
                    continue
                quote = (res.get("quote") or "").strip()
                off = find_quote_offset(ctext, quote) if quote else None
                verified = off is not None
                mappings.append(
                    {
                        "proposition": proposition,
                        "doc_quote": doc_quote or None,
                        "doc_span_start": doc_off[0] if doc_off else None,
                        "doc_span_end": doc_off[1] if doc_off else None,
                        "source": source,
                        "case_name": case_name,
                        "citation": cite,
                        "source_ref": source_ref,
                        "source_url": source_url,
                        "support_quote": quote or None,
                        "source_span_start": off[0] if off else None,
                        "source_span_end": off[1] if off else None,
                        "verified": 1 if verified else 0,
                        "relevance": float(res.get("relevance") or 0.0),
                        "note": None
                        if verified
                        else "Quote could not be located verbatim in the source — treat as unverified.",
                        "reasoning": self._clean_reasoning(res),
                    }
                )

        verified_count = sum(1 for m in mappings if m["verified"])
        summary = {
            "propositions": len(props),
            "authorities": len(mappings),
            "verified": verified_count,
            "courtlistener": len(mappings),
        }

        async with AsyncSessionLocal() as db:
            db.add(
                AuthorityMapRun(
                    id=run_id,
                    user_id=user_id,
                    document_id=document_id,
                    document_name=document_name,
                    document_length_chars=len(text),
                    jurisdiction=jurisdiction,
                    propositions_found=len(props),
                    authorities_found=len(mappings),
                    verified_count=verified_count,
                    summary=summary,
                    is_complete=1,
                    completed_at=datetime.utcnow(),
                )
            )
            for m in mappings:
                db.add(AuthorityMapping(run_id=run_id, **m))
            await db.commit()

        return {
            "run_id": run_id,
            "document_name": document_name,
            "jurisdiction": jurisdiction,
            "summary": summary,
            "mappings": mappings,
        }


authority_mapper_service = AuthorityMapperService()
