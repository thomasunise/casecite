"""Redlines: span-grounded LLM redrafts + deterministic tracked-change .docx."""

import json
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

from app.services.ai_notice import AI_REVIEW_NOTICE
from app.services.contract_analysis.redlines import (
    generate_redlines,
    reconstruct_original_text,
    render_redline_docx,
)
from docx import Document

CONTRACT = (
    "MASTER SERVICES AGREEMENT\n"
    "1. TERM. This Agreement begins on the Effective Date and renews automatically "
    "for successive one-year terms unless either party gives notice.\n"
    "2. LIABILITY. Provider's liability is unlimited for all claims of any kind.\n"
    "3. GOVERNING LAW. This Agreement is governed by the laws of Delaware.\n"
)

LIABILITY = "Provider's liability is unlimited for all claims of any kind."
LIABILITY_START = CONTRACT.index(LIABILITY)
LIABILITY_END = LIABILITY_START + len(LIABILITY)


def _span_issue(ref="risk-0", severity="critical", start=LIABILITY_START, end=LIABILITY_END):
    return {
        "ref": ref,
        "title": "Unlimited liability",
        "severity": severity,
        "why": "Exposes the client to uncapped damages.",
        "suggested_language": None,
        "span_start": start,
        "span_end": end,
        "matched_text": CONTRACT[start:end][:200],
        "grounding": "span",
    }


def _absence_issue(
    suggested="Confidentiality. Each party shall protect the other's Confidential Information.",
):
    return {
        "ref": "miss-0",
        "title": "Missing clause: confidentiality",
        "severity": "major",
        "why": "No confidentiality protection at all.",
        "suggested_language": suggested,
        "span_start": None,
        "span_end": None,
        "matched_text": "",
        "grounding": "absence",
    }


def _client_returning(*payloads):
    """MagicMock client whose successive create() calls return the given payloads.

    A payload that is an Exception instance is raised instead.
    """
    responses = []
    for p in payloads:
        if isinstance(p, Exception):
            responses.append(p)
        else:
            r = MagicMock()
            r.choices = [MagicMock()]
            r.choices[0].message.content = json.dumps(p)
            responses.append(r)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=responses)
    return client


class TestGenerateRedlines:
    async def test_span_issue_becomes_replace_edit(self):
        proposed = "Provider's aggregate liability is capped at fees paid in the prior 12 months."
        client = _client_returning({"proposed_text": proposed, "rationale": "Caps exposure."})
        edits = await generate_redlines(client, CONTRACT, [_span_issue()])
        assert len(edits) == 1
        e = edits[0]
        assert e["kind"] == "replace"
        assert e["ref"] == "risk-0"
        assert e["original_text"] == CONTRACT[LIABILITY_START:LIABILITY_END]
        assert e["proposed_text"] == proposed
        assert e["rationale"] == "Caps exposure."
        assert e["severity"] == "critical"
        assert e["title"] == "Unlimited liability"
        assert (e["span_start"], e["span_end"]) == (LIABILITY_START, LIABILITY_END)

    async def test_absence_issue_becomes_insert_without_llm(self):
        client = _client_returning()  # any create() call would raise StopIteration
        edits = await generate_redlines(client, CONTRACT, [_absence_issue()])
        assert client.chat.completions.create.await_count == 0
        assert len(edits) == 1
        e = edits[0]
        assert e["kind"] == "insert"
        assert e["span_start"] == e["span_end"] == len(CONTRACT)
        assert e["original_text"] == ""
        assert e["proposed_text"].startswith("Confidentiality.")
        assert e["ref"] == "miss-0"

    async def test_absence_without_suggested_language_is_skipped(self):
        edits = await generate_redlines(
            _client_returning(), CONTRACT, [_absence_issue(suggested="")]
        )
        assert edits == []

    async def test_identical_proposed_text_is_skipped(self):
        client = _client_returning({"proposed_text": LIABILITY, "rationale": "no-op"})
        edits = await generate_redlines(client, CONTRACT, [_span_issue()])
        assert edits == []

    async def test_empty_proposed_text_is_skipped(self):
        client = _client_returning({"proposed_text": "", "rationale": "punt"})
        edits = await generate_redlines(client, CONTRACT, [_span_issue()])
        assert edits == []

    async def test_unverified_and_spanless_issues_are_skipped(self):
        issues = [
            {**_span_issue(ref="gen-0"), "grounding": "unverified"},
            {**_span_issue(ref="dev-0"), "span_start": None, "span_end": None},
        ]
        client = _client_returning()
        edits = await generate_redlines(client, CONTRACT, issues)
        assert edits == []
        assert client.chat.completions.create.await_count == 0

    async def test_one_llm_failure_does_not_kill_the_batch(self):
        term = "This Agreement begins on the Effective Date"
        t_start = CONTRACT.index(term)
        issues = [
            _span_issue(ref="risk-0", severity="critical"),
            _span_issue(ref="dev-0", severity="major", start=t_start, end=t_start + len(term)),
        ]
        # Calls are dispatched in severity order: critical first (fails), major second.
        client = _client_returning(
            ConnectionError("llm down"),
            {"proposed_text": "This Agreement begins on the Signature Date", "rationale": "r"},
        )
        edits = await generate_redlines(client, CONTRACT, issues)
        assert len(edits) == 1
        assert edits[0]["ref"] == "dev-0"

    async def test_cap_at_30_most_severe_critical_first(self):
        lines = [f"Clause {i}: obligation number {i} applies here." for i in range(30)]
        text = "\n".join(lines)
        issues = []
        pos = 0
        for i, line in enumerate(lines):
            severity = "critical" if i >= 27 else "minor"  # criticals live at the END
            issues.append(
                {
                    "ref": f"risk-{i}",
                    "title": f"Issue {i}",
                    "severity": severity,
                    "why": "w",
                    "suggested_language": None,
                    "span_start": pos,
                    "span_end": pos + len(line),
                    "matched_text": line,
                    "grounding": "span",
                }
            )
            pos += len(line) + 1
        client = _client_returning(
            *({"proposed_text": f"Redrafted clause {i}.", "rationale": "r"} for i in range(30))
        )
        edits = await generate_redlines(client, text, issues)
        assert client.chat.completions.create.await_count == 30
        assert len(edits) == 30
        refs = {e["ref"] for e in edits}
        # All three criticals made the cut despite appearing last in the list.
        assert {"risk-27", "risk-28", "risk-29"} <= refs
        # Result is sorted by span_start.
        starts = [e["span_start"] for e in edits]
        assert starts == sorted(starts)

    async def test_insertions_sort_last(self):
        proposed = "Provider's liability is capped."
        client = _client_returning({"proposed_text": proposed, "rationale": "r"})
        edits = await generate_redlines(client, CONTRACT, [_absence_issue(), _span_issue()])
        assert [e["kind"] for e in edits] == ["replace", "insert"]


def _document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8")


def _replace_edit(proposed="Provider's aggregate liability is capped at prior 12 months' fees."):
    return {
        "ref": "risk-0",
        "kind": "replace",
        "span_start": LIABILITY_START,
        "span_end": LIABILITY_END,
        "original_text": LIABILITY,
        "proposed_text": proposed,
        "rationale": "Caps exposure.",
        "severity": "critical",
        "title": "Unlimited liability",
    }


def _insert_edit():
    return {
        "ref": "miss-0",
        "kind": "insert",
        "span_start": len(CONTRACT),
        "span_end": len(CONTRACT),
        "original_text": "",
        "proposed_text": "Each party shall keep Confidential Information secret.",
        "rationale": None,
        "severity": "major",
        "title": "Missing clause: confidentiality",
    }


class TestRenderRedlineDocx:
    def test_bytes_are_a_valid_docx_with_tracked_changes(self):
        out = render_redline_docx(CONTRACT, [_replace_edit(), _insert_edit()])
        assert isinstance(out, bytes)
        assert out[:2] == b"PK"
        doc = Document(BytesIO(out))  # round-trips cleanly
        assert doc.paragraphs
        xml = _document_xml(out)
        assert "<w:del " in xml
        assert "<w:ins " in xml
        assert "w:delText" in xml

    def test_deleted_original_and_inserted_proposed_text_present(self):
        proposed = "Provider's aggregate liability is capped at prior 12 months' fees."
        xml = _document_xml(render_redline_docx(CONTRACT, [_replace_edit(proposed)]))
        del_block = xml[xml.index("<w:del ") : xml.index("</w:del>")]
        assert LIABILITY in del_block
        ins_block = xml[xml.index("<w:ins ") : xml.index("</w:ins>")]
        assert proposed in ins_block
        # Revision marks carry author/date/id.
        assert 'w:author="CaseCite"' in xml
        assert "w:date=" in xml
        assert "w:id=" in xml

    def test_untouched_text_renders_as_plain_runs(self):
        out = render_redline_docx(CONTRACT, [_replace_edit()])
        doc = Document(BytesIO(out))
        full = "\n".join(p.text for p in doc.paragraphs)
        assert "MASTER SERVICES AGREEMENT" in full
        assert "GOVERNING LAW" in full

    def test_insertion_appended_with_heading(self):
        xml = _document_xml(render_redline_docx(CONTRACT, [_insert_edit()]))
        assert "Proposed addition — Missing clause: confidentiality" in xml
        ins_block = xml[xml.index("<w:ins ") : xml.index("</w:ins>")]
        assert "Each party shall keep Confidential Information secret." in ins_block
        assert "<w:del " not in xml

    def test_empty_edits_produce_plain_document(self):
        out = render_redline_docx(CONTRACT, [])
        assert out[:2] == b"PK"
        doc = Document(BytesIO(out))
        assert [p.text for p in doc.paragraphs][: len(CONTRACT.split("\n"))] == CONTRACT.split("\n")
        xml = _document_xml(out)
        assert "<w:del " not in xml
        assert "<w:ins " not in xml

    def test_multiparagraph_edit_does_not_corrupt_later_edits(self):
        # Edit 1 spans from inside paragraph 2 across the newline into paragraph 3.
        start1 = CONTRACT.index("renews automatically")
        end1 = CONTRACT.index("unlimited") + len("unlimited")  # crosses into clause 2
        edit1 = {
            "ref": "dev-0",
            "kind": "replace",
            "span_start": start1,
            "span_end": end1,
            "original_text": CONTRACT[start1:end1],
            "proposed_text": "renews only by mutual written agreement. 2. LIABILITY. Liability is capped",
            "rationale": None,
            "severity": "major",
            "title": "Auto-renewal",
        }
        gl = "This Agreement is governed by the laws of Delaware."
        start2 = CONTRACT.index(gl)
        edit2 = {
            "ref": "risk-1",
            "kind": "replace",
            "span_start": start2,
            "span_end": start2 + len(gl),
            "original_text": gl,
            "proposed_text": "This Agreement is governed by the laws of New York.",
            "rationale": None,
            "severity": "minor",
            "title": "Governing law",
        }
        out = render_redline_docx(CONTRACT, [edit1, edit2])
        Document(BytesIO(out))  # still opens cleanly
        xml = _document_xml(out)
        # Later edit landed on its own clause, offsets uncorrupted.
        assert "laws of New York." in xml
        last_del = xml[xml.rindex("<w:del ") : xml.rindex("</w:del>")]
        assert gl in last_del
        # The multi-paragraph deletion is rendered per paragraph it touches —
        # each paragraph's share of the span appears as its own w:delText, so
        # the document's plain + deleted text is still the contract verbatim.
        part1, part2 = CONTRACT[start1:end1].split("\n")
        assert f'<w:delText xml:space="preserve">{part1}</w:delText>' in xml
        assert f'<w:delText xml:space="preserve">{part2}</w:delText>' in xml
        assert CONTRACT[start1:end1].replace("\n", " ") not in xml
        from app.services.contract_analysis.redlines import reconstruct_original_text

        assert reconstruct_original_text(out, CONTRACT.count("\n") + 1) == CONTRACT

    def test_empty_text_no_crash(self):
        out = render_redline_docx("", [])
        assert out[:2] == b"PK"
        Document(BytesIO(out))


class TestReviewNotice:
    """The notice is the final paragraph, after the contract body, proposed
    additions and export notes, and never disturbs the fidelity check."""

    def test_notice_is_last_paragraph_after_additions_and_notes(self):
        text = "Clause one.\nClause two."
        insert = {
            "kind": "insert",
            "title": "Add limitation",
            "proposed_text": "Liability is capped.",
        }
        omitted = {"title": "Lost edit", "original_text": "gone"}
        out = render_redline_docx(text, [insert], omitted=[omitted])
        paragraphs = [p.text for p in Document(BytesIO(out)).paragraphs]
        assert paragraphs[-1] == AI_REVIEW_NOTICE
        assert paragraphs.index("Export notes") < len(paragraphs) - 1
        assert any(p.startswith("Proposed addition") for p in paragraphs[:-2])
        assert reconstruct_original_text(out, text.count("\n") + 1) == text

    def test_notice_present_without_edits(self):
        out = render_redline_docx("Only clause.", [])
        doc = Document(BytesIO(out))
        assert doc.paragraphs[-1].text == AI_REVIEW_NOTICE
        assert all(run.italic for run in doc.paragraphs[-1].runs)
