"""
Redline export fidelity: what leaves the building is the contract, verbatim.

Covers the three failure modes the audit found — duplicated text at vector-chunk
seams, edits anchored to reconstructed rather than original text, and a
renderer that could silently drop or reflow text — plus the guard that would
catch a regression in any of them.
"""

from app.services.contract_analysis.redlines import (
    CLAUSE_EXCERPT_CHARS,
    MAX_REDLINE_SPAN_CHARS,
    TEXT_CAP,
    reconstruct_original_text,
    relocate_edits,
    render_redline_docx,
)
from app.services.contract_analysis.service import merge_overlapping_chunks

CONTRACT = (
    "MASTER SERVICES AGREEMENT\n"
    "1. TERM. This Agreement begins on the Effective Date and renews automatically "
    "for successive one-year terms unless either party gives notice.\n"
    "\n"
    "2. LIABILITY. Provider's liability is unlimited for all claims of any kind.\n"
    "3. GOVERNING LAW. This Agreement is governed by the laws of Delaware.\n"
    "4. NOTICES. Notices must be in writing.\n"
)


def _edit(original: str, proposed: str, ref: str = "r0", start: int | None = None) -> dict:
    s = CONTRACT.index(original) if start is None else start
    return {
        "ref": ref,
        "kind": "replace",
        "span_start": s,
        "span_end": s + len(original),
        "original_text": original,
        "proposed_text": proposed,
        "rationale": None,
        "severity": "critical",
        "title": f"Edit {ref}",
    }


def _paragraphs(text: str) -> int:
    return text.count("\n") + 1


class TestChunkSeamMerge:
    def test_overlapping_seams_are_dropped(self):
        # Non-periodic prose (numbered words), sliced like the chunker does:
        # 500-char windows advancing 400, so each repeats the prior 100 chars.
        text = " ".join(f"word{i:04d}" for i in range(400))
        chunks = [text[i : i + 500] for i in range(0, len(text), 400)]
        assert len(chunks) > 5
        assert merge_overlapping_chunks(chunks) == text

    def test_real_sentences_are_not_duplicated(self):
        chunks = [
            "1. TERM. This Agreement begins on the Effective Date. 2. LIABILITY. Provider's",
            "2. LIABILITY. Provider's liability is unlimited for all claims.",
        ]
        merged = merge_overlapping_chunks(chunks)
        assert merged.count("2. LIABILITY.") == 1
        assert merged.endswith("for all claims.")

    def test_non_overlapping_chunks_keep_newline_join(self):
        assert merge_overlapping_chunks(["alpha", "beta"]) == "alpha\nbeta"

    def test_short_coincidental_overlap_is_not_a_seam(self):
        # 19-char shared run is below the seam threshold → treated as distinct text.
        assert merge_overlapping_chunks(["xx the party shall", "the party shall yy"]) == (
            "xx the party shall\nthe party shall yy"
        )

    def test_trailing_chunk_entirely_inside_previous(self):
        # The last chunk of a document can be shorter than the overlap window,
        # i.e. wholly repeated text — it must contribute nothing.
        prev = "the last clause of this agreement survives termination for five years."
        tail = prev[-40:]
        assert merge_overlapping_chunks([prev, tail]) == prev

    def test_empty_chunks_skipped(self):
        assert merge_overlapping_chunks(["", "hello", ""]) == "hello"


class TestRelocateEdits:
    def test_edits_from_chunk_text_are_re_anchored_on_source(self):
        # Analysis ran on a seam-duplicated reconstruction; offsets are wrong for the source.
        chunk_text = CONTRACT.replace("3. GOVERNING LAW.", "of any kind.\n3. GOVERNING LAW.")
        original = "Provider's liability is unlimited for all claims of any kind."
        stored = _edit(original, "Liability is capped.", start=chunk_text.index(original))
        located, omitted = relocate_edits(CONTRACT, [stored])
        assert omitted == []
        assert CONTRACT[located[0]["span_start"] : located[0]["span_end"]] == original

    def test_whitespace_differences_are_tolerated(self):
        stored = _edit("This Agreement is governed by the laws of Delaware.", "Governed by NY law.")
        stored["original_text"] = "This Agreement is  governed by\nthe laws of Delaware."
        located, omitted = relocate_edits(CONTRACT, [stored])
        assert omitted == []
        assert CONTRACT[located[0]["span_start"] : located[0]["span_end"]] == (
            "This Agreement is governed by the laws of Delaware."
        )

    def test_unlocatable_edit_is_omitted_not_guessed(self):
        stored = _edit("Provider's liability is unlimited for all claims of any kind.", "x")
        stored["original_text"] = "This sentence does not appear in the contract at all."
        located, omitted = relocate_edits(CONTRACT, [stored])
        assert located == []
        assert omitted == [stored]

    def test_repeated_text_resolves_in_document_order(self):
        text = "Clause A. Notice must be in writing.\nClause B. Notice must be in writing.\n"
        first = _edit("Notice must be in writing.", "First.", ref="a", start=10)
        second = _edit("Notice must be in writing.", "Second.", ref="b", start=47)
        located, _ = relocate_edits(text, [first, second])
        assert [e["ref"] for e in located] == ["a", "b"]
        assert located[0]["span_start"] < located[1]["span_start"]

    def test_insertions_move_to_end_of_source(self):
        ins = {
            "ref": "m0",
            "kind": "insert",
            "span_start": 5,
            "span_end": 5,
            "original_text": "",
            "proposed_text": "New clause.",
            "title": "Add",
        }
        located, omitted = relocate_edits(CONTRACT, [ins])
        assert omitted == []
        assert located[0]["span_start"] == located[0]["span_end"] == len(CONTRACT)


class TestRenderFidelity:
    def test_untouched_document_round_trips_exactly(self):
        out = render_redline_docx(CONTRACT, [])
        assert reconstruct_original_text(out, _paragraphs(CONTRACT)) == CONTRACT

    def test_single_edit_round_trips_exactly(self):
        edit = _edit(
            "Provider's liability is unlimited for all claims of any kind.",
            "Provider's aggregate liability is capped at fees paid.",
        )
        out = render_redline_docx(CONTRACT, [edit])
        assert reconstruct_original_text(out, _paragraphs(CONTRACT)) == CONTRACT

    def test_edit_spanning_paragraphs_round_trips_exactly(self):
        """The deleted span is emitted per paragraph it touches — nothing consumed."""
        original = (
            "2. LIABILITY. Provider's liability is unlimited for all claims of any kind.\n"
            "3. GOVERNING LAW. This Agreement is governed by the laws of Delaware."
        )
        edit = _edit(original, "2. LIABILITY AND LAW. Capped; Delaware law.")
        out = render_redline_docx(CONTRACT, [edit])
        assert reconstruct_original_text(out, _paragraphs(CONTRACT)) == CONTRACT

    def test_edit_ending_at_paragraph_end_and_starting_at_paragraph_start(self):
        text = "First line.\nSecond line.\nThird line.\n"
        edits = [
            _edit("First line.", "1st.", ref="a", start=0),
            _edit("Second line.\nThird line.", "Rest.", ref="b", start=text.index("Second")),
        ]
        out = render_redline_docx(text, edits)
        assert reconstruct_original_text(out, _paragraphs(text)) == text

    def test_edit_covering_the_newline_only(self):
        text = "Alpha\nBeta\n"
        edit = _edit("\n", " ", ref="nl", start=5)
        out = render_redline_docx(text, [edit])
        assert reconstruct_original_text(out, _paragraphs(text)) == text

    def test_empty_paragraphs_inside_a_span(self):
        text = "One\n\n\nFour\n"
        edit = _edit("One\n\n\nFour", "All.", ref="x", start=0)
        out = render_redline_docx(text, [edit])
        assert reconstruct_original_text(out, _paragraphs(text)) == text

    def test_omitted_edits_are_listed_in_export_notes(self):
        import zipfile
        from io import BytesIO

        dropped = _edit("Provider's liability is unlimited for all claims of any kind.", "x")
        dropped["title"] = "Unlimited liability"
        out = render_redline_docx(CONTRACT, [], omitted=[dropped])
        with zipfile.ZipFile(BytesIO(out)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        assert "Export notes" in xml
        assert "1 proposed change(s) could not be located" in xml
        assert "Unlimited liability" in xml
        # The contract itself is still intact ahead of the notes.
        assert reconstruct_original_text(out, _paragraphs(CONTRACT)) == CONTRACT

    def test_reconstruction_detects_tampering(self):
        out = render_redline_docx(CONTRACT, [])
        assert reconstruct_original_text(out, _paragraphs(CONTRACT)) != CONTRACT.replace(
            "Delaware", "Nevada"
        )


class TestRedraftSeesWholeSpan:
    def test_excerpt_and_stored_text_cover_the_full_redlinable_span(self):
        # A redraft of a truncated clause that then deletes the untruncated span
        # would silently drop the clause's tail — the caps must agree.
        assert CLAUSE_EXCERPT_CHARS == MAX_REDLINE_SPAN_CHARS
        assert TEXT_CAP == MAX_REDLINE_SPAN_CHARS
