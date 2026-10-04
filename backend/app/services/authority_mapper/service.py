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

The document and each candidate opinion are read in windows, so text past the
first window is not ignored. The work is still bounded (a cap on windows and on
propositions researched); whatever the bounds leave out is reported in the
run's ``summary["coverage"]`` rather than passed over in silence.
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
# The document and each opinion are read window by window. Windows overlap so
# a sentence straddling a boundary is still seen whole in one of them.
WINDOW_CHARS = 60_000
WINDOW_OVERLAP = 2_000
MAX_DOCUMENT_WINDOWS = max(1, int(getattr(settings, "authority_map_max_document_windows", 8)))
MAX_OPINION_WINDOWS = max(1, int(getattr(settings, "authority_map_max_opinion_windows", 4)))


def _windows(text: str, max_windows: int) -> tuple[list[str], int]:
    """Split ``text`` into overlapping windows, at most ``max_windows`` of them.

    Returns (windows, chars_covered): ``chars_covered < len(text)`` means the
    cap left the tail unread.
    """
    if len(text) <= WINDOW_CHARS:
        return [text], len(text)
    windows: list[str] = []
    covered = 0
    step = WINDOW_CHARS - WINDOW_OVERLAP
    for start in range(0, len(text), step):
        if len(windows) >= max_windows:
            break
        windows.append(text[start : start + WINDOW_CHARS])
        covered = min(len(text), start + WINDOW_CHARS)
        if covered >= len(text):
            break
    return windows, covered


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

    async def _extract_window_propositions(self, client, window: str, part: str) -> list[dict]:
        # Imported here: app.services.rag imports this module's package.
        from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block

        prompt = (
            "You are a litigation research assistant. Read the document and identify the "
            "key legal propositions or factual assertions that would benefit from supporting "
            "case-law authority. For each, copy the EXACT verbatim quote from the document "
            "(character-for-character, do not paraphrase) and give a short search query a "
            "lawyer would use to find supporting cases.\n\n"
            'Return STRICT JSON: {"propositions":[{"proposition":"...","doc_quote":"...verbatim...",'
            '"query":"..."}]}.\n'
            f"Return at most {MAX_PROPOSITIONS} of the most important, most important first.\n\n"
            f"{UNTRUSTED_CONTENT_RULE}\n\n"
            f"DOCUMENT ({part}):\n" + untrusted_block(f"Document, {part}", window)
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
        return [p for p in props if isinstance(p, dict)][:MAX_PROPOSITIONS]

    async def _extract_propositions(self, client, text: str) -> tuple[list[dict], dict]:
        """Propositions from across the WHOLE document, plus what was covered.

        Every window is read. The propositions researched are then drawn from
        the windows in turn (each window's most important first), so a long
        filing's later sections are represented instead of the first pages
        using up the whole budget.
        """
        windows, covered = _windows(text, MAX_DOCUMENT_WINDOWS)
        per_window: list[list[dict]] = []
        failures = 0
        last_error: Exception | None = None
        for index, window in enumerate(windows):
            part = f"part {index + 1} of {len(windows)}"
            try:
                per_window.append(await self._extract_window_propositions(client, window, part))
            except Exception as e:  # one window failing must not lose the others
                failures += 1
                last_error = e
                logger.warning(f"proposition extraction failed for {part}: {e}")
                per_window.append([])
        if failures == len(windows) and last_error is not None:
            raise last_error

        selected: list[dict] = []
        seen: set[str] = set()
        identified = 0
        depth = max((len(props) for props in per_window), default=0)
        for rank in range(depth):
            for props in per_window:
                if rank >= len(props):
                    continue
                prop = props[rank]
                key = _normalize_ws(str(prop.get("doc_quote") or prop.get("proposition") or ""))
                if not key or key.lower() in seen:
                    continue
                seen.add(key.lower())
                identified += 1
                if len(selected) < MAX_PROPOSITIONS:
                    selected.append(prop)

        coverage = {
            "document_chars": len(text),
            "document_chars_read": covered,
            "document_windows_read": len(windows) - failures,
            "document_windows_failed": failures,
            "document_truncated": covered < len(text),
            "propositions_identified": identified,
            "propositions_researched": len(selected),
            "propositions_limit": MAX_PROPOSITIONS,
        }
        return selected, coverage

    async def _check_support(
        self, client, proposition: str, source_name: str, source_text: str
    ) -> dict:
        """Look for supporting language anywhere in the source, window by window.

        Returns the first window's verdict that finds support. ``partially_read``
        is set when the source was longer than MAX_OPINION_WINDOWS windows and
        no support was found in the part that was read.
        """
        windows, covered = _windows(source_text, MAX_OPINION_WINDOWS)
        res: dict = {}
        for index, window in enumerate(windows):
            part = f"part {index + 1} of {len(windows)}"
            res = await self._check_support_window(client, proposition, source_name, window, part)
            if res.get("supports"):
                return res
        res = dict(res) if isinstance(res, dict) else {}
        res["partially_read"] = covered < len(source_text)
        return res

    async def _check_support_window(
        self, client, proposition: str, source_name: str, window: str, part: str
    ) -> dict:
        from app.services.rag.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block

        prompt = (
            "A lawyer needs authority supporting this proposition:\n"
            f'"{proposition}"\n\n'
            f"Below is the text of {source_name} ({part}). If — and only if — it contains language that "
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
            f"{UNTRUSTED_CONTENT_RULE}\n\n"
            "SOURCE:\n" + untrusted_block(f"Source text, {part}", window)
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

        props, coverage = await self._extract_propositions(client, text)
        mappings: list[dict] = []
        opinions_checked = 0
        opinions_partially_read = 0

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
                opinions_checked += 1
                if not res.get("supports"):
                    if res.get("partially_read"):
                        opinions_partially_read += 1
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
            # What the bounds left out, so the UI never has to imply the whole
            # document (or every opinion) was read when it was not.
            "coverage": {
                **coverage,
                "opinions_checked": opinions_checked,
                "opinions_partially_read": opinions_partially_read,
            },
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
