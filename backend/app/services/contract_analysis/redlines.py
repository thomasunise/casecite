"""Contract redlining: issue-driven edits rendered as genuine Word tracked changes.

Two-stage pipeline:

  generate_redlines()   — async; for each span-grounded issue, ONE utility-LLM
                          call redrafts the offending clause as a drop-in
                          replacement. Absence-grounded issues with suggested
                          language become deterministic insertions (no LLM).
                          Same grounding discipline as the rest of the
                          contract pipeline: the original text is taken
                          verbatim from the document by its span offsets — the
                          model only ever proposes the replacement.

  relocate_edits()      — sync; re-anchors stored edits onto a different copy
                          of the contract text (the text extracted from the
                          stored original file rather than the vector-chunk
                          reconstruction the analysis ran on) by locating each
                          edit's verbatim ``original_text``. Edits that cannot
                          be located are returned separately, never guessed.

  render_redline_docx() — sync, deterministic, no LLM; renders the FULL
                          contract text into a .docx where every edit is a
                          native OOXML tracked change (``w:del`` around the
                          original run, ``w:ins`` around the proposed run) so
                          Word shows its own accept/reject UI. python-docx
                          doesn't expose tracked changes, so the revision
                          elements are built directly with ``docx.oxml``.
                          Every character of the input text is emitted either
                          as a plain run or inside a ``w:delText`` — nothing
                          is dropped or reflowed — which
                          reconstruct_original_text() verifies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from app.services.ai_notice import add_docx_notice
from app.services.llm_clients import openai_chat, utility_model

logger = logging.getLogger(__name__)

# Most-severe-first processing order (matches issues.py).
_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}

MAX_REDLINE_ISSUES = 30
_CONCURRENCY = 6
# Cap redlines at clause/section scale (the redraft excerpt size). In an
# accept/reject workflow more proposals beats fewer — the user is the filter —
# so this only excludes spans too big to redraft coherently at all.
MAX_REDLINE_SPAN_CHARS = 4_000
# The model must see, and the stored edit must carry, the WHOLE span it
# replaces: a redraft of a truncated clause deleting the untruncated span
# would silently drop the tail of the clause from the document.
CLAUSE_EXCERPT_CHARS = MAX_REDLINE_SPAN_CHARS
TEXT_CAP = MAX_REDLINE_SPAN_CHARS


def _valid_span(text: str, issue: dict[str, Any]) -> bool:
    start, end = issue.get("span_start"), issue.get("span_end")
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(text)
        and (end - start) <= MAX_REDLINE_SPAN_CHARS
    )


def _severity_rank(issue: dict[str, Any]) -> int:
    return _SEVERITY_ORDER.get(str(issue.get("severity") or "").lower(), len(_SEVERITY_ORDER))


_SOURCE_LABELS = {
    "ai": "Identified by AI review against your instructions",
    "deviation": "Deviates from the market-standard {clause} clause",
    "missing": "Standard {clause} clause not found in this contract",
    "jurisdiction": "Jurisdiction rule for the {clause} clause",
    "risk": "Triggered a contract risk rule",
    "general_risk": "Flagged in the full-contract review",
    "general_missing": "Flagged as missing in the full-contract review",
    "general_unusual": "Flagged as unusual in the full-contract review",
}


def _edit_source(issue: dict[str, Any]) -> str:
    """Human-readable basis: where this proposal came from."""
    kind = str(issue.get("source_kind") or "")
    clause = str(issue.get("clause_slug") or "this").replace("_", " ")
    template = _SOURCE_LABELS.get(kind, "Flagged in the contract review")
    return template.format(clause=clause)


async def _redraft_clause(
    client,
    sem: asyncio.Semaphore,
    text: str,
    issue: dict[str, Any],
    instructions: str | None = None,
) -> dict[str, Any] | None:
    """One LLM call: redraft the clause at the issue's span. None on skip/failure."""
    start, end = issue["span_start"], issue["span_end"]
    original = text[start:end]
    excerpt = original[:CLAUSE_EXCERPT_CHARS]

    suggested = issue.get("suggested_language")
    suggested_note = f"\nSUGGESTED DIRECTION: {suggested}" if suggested else ""
    # The user's own framing (who they represent, what to push for) steers
    # the actual language, not just which issues were selected.
    instructions_note = (
        f"\nCLIENT INSTRUCTIONS (draft in their favor):\n{instructions.strip()[:1500]}"
        if instructions and instructions.strip()
        else ""
    )
    prompt = (
        "You are redlining one clause of a contract. Redraft the clause below "
        "to fix the identified issue. The redraft must be a DROP-IN REPLACEMENT "
        "for the clause text exactly as given — same scope and subject matter, "
        "same defined terms and party names, redrafted only as needed to fix "
        "the issue. Do not add commentary, headings, or surrounding text.\n\n"
        f"ISSUE: {issue.get('title') or ''}\n"
        f"WHY IT MATTERS: {issue.get('why') or ''}"
        f"{suggested_note}{instructions_note}\n\n"
        f"CLAUSE TEXT:\n{excerpt}\n\n"
        'Return STRICT JSON: {"proposed_text": "the full replacement clause '
        'text", "rationale": "one sentence"}'
    )
    try:
        async with sem:
            resp = await openai_chat(
                client,
                model=utility_model(),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:  # one bad redline never kills the batch
        logger.warning("redline generation failed for %s: %s", issue.get("ref"), e)
        return None

    proposed = str(data.get("proposed_text") or "").strip()
    if not proposed or proposed == excerpt.strip():
        return None  # model punted or changed nothing — not a real edit
    rationale = str(data.get("rationale") or "").strip() or None
    return {
        "ref": issue.get("ref"),
        "kind": "replace",
        "source": _edit_source(issue),
        "span_start": start,
        "span_end": end,
        "original_text": original[:TEXT_CAP],
        "proposed_text": proposed[:TEXT_CAP],
        "rationale": rationale,
        "severity": issue.get("severity"),
        "title": issue.get("title"),
    }


async def generate_redlines(
    client, text: str, issues: list[dict], instructions: str | None = None
) -> list[dict]:
    """Turn analysis issues into concrete edits.

    Span-grounded issues (most severe first, capped at MAX_REDLINE_ISSUES) each
    get one utility-LLM redraft of the clause at their offsets; overlapping
    spans are dropped in favor of the more severe issue so the rendered
    document stays consistent. Absence-grounded issues with suggested language
    become deterministic append-at-end insertions.

    Per-issue LLM failures are logged and skipped, never fatal. Returns edits
    sorted by span_start with insertions last:
      {ref, kind: "replace"|"insert", span_start, span_end, original_text,
       proposed_text, rationale, severity, title}
    """
    edits: list[dict[str, Any]] = []

    # --- replacements: span-grounded, most severe first, non-overlapping ---
    candidates = [
        i
        for i in issues
        if i.get("grounding") == "span"
        and i.get("status") != "info"  # "addressed" notes are not edits
        and _valid_span(text, i)
    ]
    candidates.sort(key=_severity_rank)  # stable: keeps pipeline order within severity
    selected: list[dict[str, Any]] = []
    for issue in candidates:
        if len(selected) >= MAX_REDLINE_ISSUES:
            break
        if any(
            issue["span_start"] < s["span_end"] and s["span_start"] < issue["span_end"]
            for s in selected
        ):
            continue  # overlaps a more severe issue's clause — that redline wins
        selected.append(issue)

    if client is not None and selected:
        sem = asyncio.Semaphore(_CONCURRENCY)
        results = await asyncio.gather(
            *(_redraft_clause(client, sem, text, i, instructions) for i in selected)
        )
        edits.extend(r for r in results if r is not None)

    # --- insertions: absence-grounded, deterministic, no LLM ---
    for issue in issues:
        if issue.get("grounding") != "absence":
            continue
        suggested = str(issue.get("suggested_language") or "").strip()
        if not suggested:
            continue
        edits.append(
            {
                "ref": issue.get("ref"),
                "kind": "insert",
                "source": _edit_source(issue),
                "span_start": len(text),
                "span_end": len(text),
                "original_text": "",
                "proposed_text": suggested[:TEXT_CAP],
                "rationale": None,
                "severity": issue.get("severity"),
                "title": issue.get("title"),
            }
        )

    edits.sort(key=lambda e: (e["span_start"], 1 if e["kind"] == "insert" else 0))
    return edits


# --------------------------------------------------------------------------
# Re-anchoring edits onto the source text
# --------------------------------------------------------------------------


def _find_text(haystack: str, needle: str, from_pos: int = 0) -> tuple[int, int] | None:
    """Locate ``needle`` in ``haystack`` at or after ``from_pos``, exact first,
    then tolerant of whitespace differences. Returns offsets into ``haystack``."""
    if not haystack or not needle:
        return None
    idx = haystack.find(needle, from_pos)
    if idx >= 0:
        return idx, idx + len(needle)
    tokens = needle.split()
    if len(" ".join(tokens)) < 12:  # too short to anchor confidently
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in tokens)
    try:
        m = re.compile(pattern).search(haystack, from_pos)
    except re.error:
        return None
    return (m.start(), m.end()) if m else None


def relocate_edits(source_text: str, edits: list[dict]) -> tuple[list[dict], list[dict]]:
    """Re-anchor edits onto ``source_text`` by their verbatim ``original_text``.

    Stored edits carry offsets into the text the analysis ran on. When the
    export renders a different copy of the contract (the text extracted from
    the stored original file), each replacement is located by searching for
    its original text — scanning forward from the previous edit so repeated
    boilerplate resolves in document order, then from the top as a fallback.
    Insertions are re-pointed at the end of the source text.

    Returns ``(located, omitted)``. An edit whose original text cannot be
    found is omitted rather than placed by guesswork; the caller reports it.
    """
    located: list[dict] = []
    omitted: list[dict] = []
    cursor = 0
    for edit in sorted(edits, key=lambda e: e.get("span_start") or 0):
        if edit.get("kind") == "insert":
            located.append({**edit, "span_start": len(source_text), "span_end": len(source_text)})
            continue
        original = str(edit.get("original_text") or "")
        hit = _find_text(source_text, original, cursor) or _find_text(source_text, original, 0)
        if hit is None:
            omitted.append(edit)
            continue
        start, end = hit
        located.append({**edit, "span_start": start, "span_end": end})
        cursor = max(cursor, end)
    located.sort(key=lambda e: (e["span_start"], 1 if e.get("kind") == "insert" else 0))
    return located, omitted


# --------------------------------------------------------------------------
# Tracked-change .docx rendering
# --------------------------------------------------------------------------


def _revision_attrs(el, rev_id: int, author: str, date: str) -> None:
    from docx.oxml.ns import qn

    el.set(qn("w:id"), str(rev_id))
    el.set(qn("w:author"), author)
    el.set(qn("w:date"), date)


def _plain_run(run_text: str):
    """A bare w:r/w:t run with whitespace preserved."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = run_text
    r.append(t)
    return r


def _del_element(deleted_text: str, rev_id: int, author: str, date: str):
    """w:del wrapping a run whose content is w:delText (Word's deletion mark)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    el = OxmlElement("w:del")
    _revision_attrs(el, rev_id, author, date)
    r = OxmlElement("w:r")
    dt = OxmlElement("w:delText")
    dt.set(qn("xml:space"), "preserve")
    dt.text = deleted_text
    r.append(dt)
    el.append(r)
    return el


def _ins_element(inserted_text: str, rev_id: int, author: str, date: str):
    """w:ins wrapping a normal w:r/w:t run (Word's insertion mark)."""
    from docx.oxml import OxmlElement

    el = OxmlElement("w:ins")
    _revision_attrs(el, rev_id, author, date)
    el.append(_plain_run(inserted_text))
    return el


def _flatten(value: str) -> str:
    """Collapse newlines for text living inside a single run."""
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def render_redline_docx(
    text: str,
    edits: list[dict],
    author: str = "CaseCite",
    omitted: list[dict] | None = None,
) -> bytes:
    """Render the full contract text as a .docx with native tracked changes.

    Every "replace" edit becomes one or more w:del runs (the original text as
    w:delText, one run per paragraph the span touches) followed, in the
    paragraph where the span ends, by a w:ins containing the proposed text —
    so Word offers its own accept/reject on each. "insert" edits are appended
    at the end of the document as a plain heading paragraph plus the proposed
    text inside w:ins. ``omitted`` edits (ones the caller could not anchor in
    this text) are listed in an "Export notes" section so the reviewer knows
    what is missing. Deterministic — no LLM.

    Fidelity invariant: the plain runs plus deleted text of the first
    ``text.count("\\n") + 1`` paragraphs, joined by newlines, equal ``text``
    exactly — see ``reconstruct_original_text``. Paragraph structure is the
    source text's newlines; run-level formatting of the source is not carried.
    """
    from docx import Document

    doc = Document()
    date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rev_id = 1

    replaces = sorted(
        (e for e in edits if e.get("kind") != "insert" and _valid_span(text, e)),
        key=lambda e: e["span_start"],
    )
    # Drop overlaps defensively (generate_redlines already prevents them).
    filtered: list[dict[str, Any]] = []
    for e in replaces:
        if filtered and e["span_start"] < filtered[-1]["span_end"]:
            continue
        filtered.append(e)
    replaces = filtered
    inserts = [e for e in edits if e.get("kind") == "insert" and e.get("proposed_text")]

    offset = 0  # global char offset of the current paragraph's first char
    ei = 0  # index of the first edit not yet fully rendered

    for line in text.split("\n"):
        start, end = offset, offset + len(line)
        p = doc.add_paragraph()
        pos = start
        while ei < len(replaces):
            edit = replaces[ei]
            if edit["span_start"] > end:
                break  # begins in a later paragraph
            cut = max(edit["span_start"], pos)
            seg_end = min(edit["span_end"], end)
            if cut > pos:
                p._p.append(_plain_run(text[pos:cut]))
            if seg_end > cut:
                # This paragraph's share of the deleted span, verbatim.
                p._p.append(_del_element(text[cut:seg_end], rev_id, author, date))
                rev_id += 1
            pos = max(pos, seg_end)
            if edit["span_end"] <= end:
                # The span ends here: the replacement follows its last deleted run.
                proposed = _flatten(str(edit.get("proposed_text") or ""))
                p._p.append(_ins_element(proposed, rev_id, author, date))
                rev_id += 1
                ei += 1
            else:
                break  # continues in the next paragraph
        if pos < end:
            p._p.append(_plain_run(text[pos:end]))
        offset = end + 1  # +1 consumes the newline separator

    for edit in inserts:
        heading = doc.add_paragraph()
        run = heading.add_run(f"Proposed addition — {edit.get('title') or edit.get('ref') or ''}")
        run.bold = True
        body = doc.add_paragraph()
        body._p.append(
            _ins_element(_flatten(str(edit.get("proposed_text") or "")), rev_id, author, date)
        )
        rev_id += 1

    if omitted:
        heading = doc.add_paragraph()
        run = heading.add_run("Export notes")
        run.bold = True
        doc.add_paragraph(
            f"{len(omitted)} proposed change(s) could not be located in the document text "
            "and are NOT shown as tracked changes above. Review them in CaseCite:"
        )
        for edit in omitted:
            label = edit.get("title") or edit.get("ref") or "untitled"
            snippet = _flatten(str(edit.get("original_text") or ""))[:160]
            doc.add_paragraph(f"• {label} — original text began: “{snippet}”")

    # Review notice LAST — after the contract body, proposed additions and
    # export notes — so reconstruct_original_text (which reads only the first
    # ``paragraph_count`` paragraphs) is unaffected.
    add_docx_notice(doc)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def reconstruct_original_text(docx_bytes: bytes, paragraph_count: int) -> str:
    """Rebuild the pre-redline text from a rendered .docx.

    Reads the first ``paragraph_count`` paragraphs, taking plain runs and
    deleted text in document order and ignoring insertions. For a document
    produced by ``render_redline_docx(text, ...)`` this equals ``text`` — the
    export path asserts it before returning a file, so a rendering bug can
    never silently alter contract language on the way to opposing counsel.
    """
    from lxml import etree

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(BytesIO(docx_bytes)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    paragraphs = root.findall(".//w:body/w:p", ns)[:paragraph_count]
    lines: list[str] = []
    for p in paragraphs:
        parts: list[str] = []
        for child in p:
            tag = etree.QName(child).localname
            if tag == "r":
                parts.extend(t.text or "" for t in child.findall("w:t", ns))
            elif tag == "del":
                parts.extend(t.text or "" for t in child.findall(".//w:delText", ns))
            # w:ins and everything else (pPr, bookmarks) contribute nothing
        lines.append("".join(parts))
    return "\n".join(lines)
