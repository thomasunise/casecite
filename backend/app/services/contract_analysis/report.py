"""
Contract-analysis report rendering (Markdown + DOCX exports).

Pure rendering: both functions take the same ``data`` dict (built by the
router from a ContractAnalysisRun and its child rows) and produce a
lawyer-facing report with identical structure:

  1. Title / contract type / analysis date / representing / posture
  2. Executive summary
  3. Key terms table (value + verified quote; unverified values marked)
  4. Issues grouped by severity (grounding-aware: span / absence / unverified)
  5. Parties
  6. Obligations (with linked deadlines)
  7. Deadlines
  8. Risk score

Grounding discipline carries into the export: an unverified key term or
issue is never presented as sourced — it is explicitly tagged.
"""

from __future__ import annotations

import io
from typing import Any

from app.services.ai_notice import add_docx_notice, markdown_notice

_SEVERITY_ORDER = ("critical", "major", "minor")

UNVERIFIED_ISSUE_TAG = "(unverified — model conclusion)"
UNVERIFIED_TERM_TAG = "(unverified)"
ABSENCE_NOTE = "Clause not found in document."


def _field_label(field: str) -> str:
    return str(field).replace("_", " ").strip().title()


def _title_meta(data: dict[str, Any]) -> list[tuple[str, str]]:
    """(label, value) pairs for the report header block."""
    meta: list[tuple[str, str]] = []
    if data.get("contract_type"):
        meta.append(("Contract type", str(data["contract_type"])))
    created = data.get("created_at")
    if created:
        # ISO timestamp → date part is enough for a report header.
        meta.append(("Analysis date", str(created)[:10]))
    if data.get("representing"):
        meta.append(("Representing", str(data["representing"])))
    if data.get("posture"):
        meta.append(("Posture", str(data["posture"])))
    return meta


def _grouped_issues(issues: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group issues by severity: critical/major/minor first, then any
    unexpected severities in first-appearance order."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for sev in _SEVERITY_ORDER:
        groups[sev] = []
        order.append(sev)
    for issue in issues or []:
        sev = str(issue.get("severity") or "minor").lower()
        if sev not in groups:
            groups[sev] = []
            order.append(sev)
        groups[sev].append(issue)
    return [(sev, groups[sev]) for sev in order if groups[sev]]


def _issue_quote(issue: dict[str, Any]) -> str | None:
    """The grounded quote for an issue, when one exists."""
    matched = (issue.get("matched_text") or "").strip()
    return matched or None


def _obligation_line(o: dict[str, Any]) -> str:
    subject = (o.get("subject_party") or "Unspecified party").strip() or "Unspecified party"
    action = (o.get("action") or "").strip()
    obj = (o.get("object_text") or "").strip()
    parts = [subject, action] if action else [subject]
    if obj:
        parts.append(obj)
    return " — ".join(parts)


def _linked_deadline_text(entry: Any) -> str:
    """An obligation's `deadlines` JSON entries are loosely-shaped dicts."""
    if isinstance(entry, dict):
        text = entry.get("description") or entry.get("matched_text") or entry.get("kind")
        if text:
            return str(text)
        return ", ".join(f"{k}: {v}" for k, v in entry.items())
    return str(entry)


def _deadline_line(d: dict[str, Any]) -> str:
    desc = (d.get("description") or d.get("matched_text") or "Deadline").strip()
    resolved = d.get("resolved_date")
    if resolved:
        return f"{desc} — resolved date: {str(resolved)[:10]}"
    return desc


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = ["# Contract Analysis Report", ""]

    for label, value in _title_meta(data):
        lines.append(f"**{label}:** {value}  ")
    if lines[-1] != "":
        lines.append("")

    summary = (data.get("executive_summary") or "").strip()
    if summary:
        lines += ["## Executive Summary", "", summary, ""]

    key_terms = data.get("key_terms") or {}
    if key_terms:
        lines += ["## Key Terms", ""]
        for field, term in key_terms.items():
            if not isinstance(term, dict):
                continue
            value = str(term.get("value") or "").strip() or "—"
            verified = bool(term.get("verified"))
            suffix = "" if verified else f" {UNVERIFIED_TERM_TAG}"
            lines.append(f"- **{_field_label(field)}** — {value}{suffix}")
            quote = (term.get("quote") or "").strip()
            if quote and verified:
                lines.append(f'  > *"{quote}"*')
        lines.append("")

    issues = data.get("issues") or []
    if issues:
        lines += ["## Issues", ""]
        for sev, group in _grouped_issues(issues):
            lines += [f"### {sev.title()}", ""]
            for issue in group:
                title = str(issue.get("title") or "Issue").strip()
                grounding = issue.get("grounding")
                if grounding == "unverified":
                    title = f"{title} {UNVERIFIED_ISSUE_TAG}"
                lines.append(f"- **{title}**")
                why = (issue.get("why") or "").strip()
                if why:
                    lines.append(f"  - Why: {why}")
                suggested = (issue.get("suggested_language") or "").strip()
                if suggested:
                    lines.append(f"  - Suggested language: {suggested}")
                if grounding == "absence":
                    lines.append(f"  - *{ABSENCE_NOTE}*")
                else:
                    quote = _issue_quote(issue)
                    if quote:
                        lines.append(f'  > *"{quote}"*')
            lines.append("")

    parties = data.get("parties") or []
    if parties:
        lines += ["## Parties", ""]
        for p in parties:
            name = str(p.get("canonical_name") or "Unknown party")
            role = (p.get("role") or "").strip()
            lines.append(f"- {name} ({role})" if role else f"- {name}")
        lines.append("")

    obligations = data.get("obligations") or []
    if obligations:
        lines += ["## Obligations", ""]
        for o in obligations:
            lines.append(f"- {_obligation_line(o)}")
            for entry in o.get("deadlines") or []:
                lines.append(f"  - Deadline: {_linked_deadline_text(entry)}")
        lines.append("")

    deadlines = data.get("deadlines") or []
    if deadlines:
        lines += ["## Deadlines", ""]
        for d in deadlines:
            lines.append(f"- {_deadline_line(d)}")
        lines.append("")

    lines += markdown_notice()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def render_docx(data: dict[str, Any]) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Contract Analysis Report", level=0)

    for label, value in _title_meta(data):
        p = doc.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(value)

    summary = (data.get("executive_summary") or "").strip()
    if summary:
        doc.add_heading("Executive Summary", level=1)
        doc.add_paragraph(summary)

    key_terms = data.get("key_terms") or {}
    if key_terms:
        doc.add_heading("Key Terms", level=1)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].paragraphs[0].add_run("Term").bold = True
        hdr[1].paragraphs[0].add_run("Value").bold = True
        for field, term in key_terms.items():
            if not isinstance(term, dict):
                continue
            row = table.add_row().cells
            row[0].text = _field_label(field)
            value = str(term.get("value") or "").strip() or "—"
            verified = bool(term.get("verified"))
            row[1].text = value if verified else f"{value} {UNVERIFIED_TERM_TAG}"
            quote = (term.get("quote") or "").strip()
            if quote and verified:
                qp = row[1].add_paragraph()
                qp.add_run(f'"{quote}"').italic = True

    issues = data.get("issues") or []
    if issues:
        doc.add_heading("Issues", level=1)
        for sev, group in _grouped_issues(issues):
            doc.add_heading(sev.title(), level=2)
            for issue in group:
                title = str(issue.get("title") or "Issue").strip()
                grounding = issue.get("grounding")
                if grounding == "unverified":
                    title = f"{title} {UNVERIFIED_ISSUE_TAG}"
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(title).bold = True
                why = (issue.get("why") or "").strip()
                if why:
                    doc.add_paragraph(f"Why: {why}", style="List Bullet 2")
                suggested = (issue.get("suggested_language") or "").strip()
                if suggested:
                    doc.add_paragraph(f"Suggested language: {suggested}", style="List Bullet 2")
                if grounding == "absence":
                    ap = doc.add_paragraph(style="List Bullet 2")
                    ap.add_run(ABSENCE_NOTE).italic = True
                else:
                    quote = _issue_quote(issue)
                    if quote:
                        qp = doc.add_paragraph(style="List Bullet 2")
                        qp.add_run(f'"{quote}"').italic = True

    parties = data.get("parties") or []
    if parties:
        doc.add_heading("Parties", level=1)
        for p_ in parties:
            name = str(p_.get("canonical_name") or "Unknown party")
            role = (p_.get("role") or "").strip()
            doc.add_paragraph(f"{name} ({role})" if role else name, style="List Bullet")

    obligations = data.get("obligations") or []
    if obligations:
        doc.add_heading("Obligations", level=1)
        for o in obligations:
            doc.add_paragraph(_obligation_line(o), style="List Bullet")
            for entry in o.get("deadlines") or []:
                doc.add_paragraph(
                    f"Deadline: {_linked_deadline_text(entry)}", style="List Bullet 2"
                )

    deadlines = data.get("deadlines") or []
    if deadlines:
        doc.add_heading("Deadlines", level=1)
        for d in deadlines:
            doc.add_paragraph(_deadline_line(d), style="List Bullet")

    add_docx_notice(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
