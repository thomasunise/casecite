"""Citation extraction, key phrase extraction, and citation building for RAG pipeline."""

import logging
import re
import uuid
from typing import Any

from app.models.schemas import (
    AnalysisMode,
    Citation,
    CitationLogic,
    CitationStatus,
    ReasoningStep,
)
from app.services.embeddings import embedding_service
from app.services.rag.prompts import get_mode_focus

logger = logging.getLogger(__name__)


def extract_cited_cases(
    content: str, case_law_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Extract which cases from case_law_results were actually cited in the AI response.
    Only returns cases that the AI explicitly mentioned.
    """
    if not case_law_results or not content:
        return []

    cited_cases = []
    content_lower = content.lower()

    for case in case_law_results:
        metadata = case.get("metadata", {})
        case_name = metadata.get("case_name", "")
        citation_str = metadata.get("citation", "")
        filename = metadata.get("filename", "")

        # Check if case name appears in response (fuzzy matching)
        if case_name:
            # Split case name into parts (e.g., "Smith v. Jones" -> ["Smith", "Jones"])
            name_parts = re.split(r"\s+v\.?\s+|\s+vs\.?\s+", case_name, flags=re.IGNORECASE)
            name_parts = [p.strip() for p in name_parts if p.strip() and len(p.strip()) > 2]

            # Check if both parties are mentioned close together (within 50 chars)
            if len(name_parts) >= 2:
                party1, party2 = name_parts[0].lower(), name_parts[1].lower()
                pattern = rf"\b{re.escape(party1)}\b.{{0,30}}\b{re.escape(party2)}\b"
                if re.search(pattern, content_lower):
                    cited_cases.append(case)
                    continue

            # Also check for exact case name match
            if case_name.lower() in content_lower:
                cited_cases.append(case)
                continue

        # Check if citation string appears (e.g., "123 F.3d 456")
        if citation_str and citation_str != "No citation":
            citation_normalized = citation_str.lower().replace(".", "").replace(",", "")
            content_normalized = content_lower.replace(".", "").replace(",", "")
            if citation_normalized in content_normalized:
                cited_cases.append(case)
                continue

        # Check filename (often contains case name + citation)
        if filename and len(filename) > 10:
            name_match = re.match(r"^([^(]+)", filename)
            if name_match:
                name_part = name_match.group(1).strip().lower()
                if len(name_part) > 5 and name_part in content_lower:
                    cited_cases.append(case)
                    continue

    return cited_cases


def extract_key_phrases(text: str, query: str) -> list[str]:
    """Extract key phrases from text that relate to query."""
    phrases = []

    # Find quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    phrases.extend(quoted[:3])

    # Find capitalized phrases (likely proper nouns, legal terms)
    caps = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text)
    phrases.extend(
        [c for c in caps if len(c) > 3 and c.lower() not in ["the", "this", "that", "these"]][:3]
    )

    # Find legal-ish terms
    legal_terms = re.findall(
        r"\b(section|clause|article|provision|requirement|compliance|regulation|statute|pursuant|herein|thereof|liability|obligation|warranty|indemnif|terminat|breach)\w*\b",
        text.lower(),
    )
    phrases.extend(list(set(legal_terms))[:3])

    # Find terms from query that appear in text
    query_words = [w.lower() for w in query.split() if len(w) > 3]
    for word in query_words:
        if word in text.lower():
            match = re.search(rf"\b(\w*{word}\w*)\b", text, re.IGNORECASE)
            if match:
                phrases.append(match.group(1))

    return list(set(phrases))[:8]


def build_document_citations(
    search_results: list[dict[str, Any]],
    query: str,
    mode: AnalysisMode,
) -> list[Citation]:
    """Build Citation objects from document search results."""
    citations = []
    for result in search_results:
        metadata = result.get("metadata", {})
        passage_text = result.get("text", "")
        filename = metadata.get("filename", "Unknown Source")
        similarity = result["similarity"]
        confidence = min(100, max(0, int(similarity * 100)))

        passage_preview = passage_text[:150].replace("\n", " ").strip()
        key_phrases = extract_key_phrases(passage_text, query)

        citation = Citation(
            id=str(uuid.uuid4()),
            source=filename,
            type=metadata.get("doc_type", "document"),
            confidence=confidence,
            status=CitationStatus.PENDING,
            similarity=similarity,
            relevance_rank=result["rank"],
            chunk_index=metadata.get("chunk_index", 0),
            token_count=embedding_service.count_tokens(passage_text),
            passage=passage_text[:500],
            reasoning=[
                ReasoningStep(
                    type="Query Analysis",
                    description=f"Analyzed query for key concepts: '{query[:80]}{'...' if len(query) > 80 else ''}'",
                    evidence=f"Analysis mode: {mode.value.title()} - focusing on {get_mode_focus(mode)}",
                ),
                ReasoningStep(
                    type="Semantic Matching",
                    description=f"Found semantic match in '{filename}' with {similarity:.1%} vector similarity",
                    evidence=f'Matched passage begins: "{passage_preview}{"..." if len(passage_text) > 150 else ""}"',
                ),
                ReasoningStep(
                    type="Content Analysis",
                    description=f"Identified relevant content in chunk #{metadata.get('chunk_index', 0) + 1} of document",
                    evidence=f"Key phrases found: {', '.join(key_phrases[:5]) if key_phrases else 'General topical relevance'}",
                ),
                ReasoningStep(
                    type="Relevance Ranking",
                    description=f"Ranked #{result['rank']} out of {len(search_results)} document matches based on similarity score",
                    evidence=f"This passage scored {similarity:.3f} similarity ({confidence}% confidence)",
                ),
            ],
            logic=CitationLogic(
                query_intent=f"User seeking information about: {query[:100]}",
                matching_criteria=f"Vector similarity: {similarity:.3f} | Document type: {metadata.get('doc_type', 'document')} | Source: {metadata.get('source', 'local')}",
                application=f"This passage from '{filename}' directly addresses the query by discussing: {passage_preview[:100]}...",
            ),
            document_id=metadata.get("document_id"),
            url=metadata.get("url"),
            was_cited_by_ai=True,
        )
        citations.append(citation)

    return citations


def build_case_law_citations(
    case_law_results: list[dict[str, Any]],
    cited_cases: list[dict[str, Any]],
    search_results_count: int,
    query: str,
) -> list[Citation]:
    """Build Citation objects from case law results, marking which were cited by AI."""
    cited_case_names = set()
    for c in cited_cases:
        name = c.get("metadata", {}).get("case_name", "")
        if name:
            cited_case_names.add(name.lower())

    citations = []
    for i, result in enumerate(case_law_results):
        metadata = result.get("metadata", {})
        passage_text = result.get("text", "")
        case_name = metadata.get("case_name", metadata.get("filename", "Unknown Case"))
        court = metadata.get("court", "Unknown Court")
        citation_str = metadata.get("citation", "No citation")
        date_filed = metadata.get("date_filed", "Unknown date")
        case_summary = metadata.get("case_summary") or None
        similarity = result.get("similarity", 0.5)
        confidence = min(100, max(0, int(similarity * 100)))

        passage_preview = (
            passage_text[:150].replace("\n", " ").strip()
            if passage_text
            else "No excerpt available"
        )
        key_phrases = extract_key_phrases(passage_text, query) if passage_text else []

        citation = Citation(
            id=str(uuid.uuid4()),
            source=metadata.get("filename", "Unknown Case"),
            type="case_law",
            confidence=confidence,
            status=CitationStatus.PENDING,
            similarity=similarity,
            relevance_rank=search_results_count + result.get("rank", i + 1),
            chunk_index=0,
            token_count=embedding_service.count_tokens(passage_text),
            passage=passage_text[:500]
            if passage_text
            else "Full text not available - click link to view on CourtListener",
            case_summary=case_summary,
            reasoning=[
                ReasoningStep(
                    type="Case Law Search",
                    description=f"Searched CourtListener database for cases matching: '{query[:60]}{'...' if len(query) > 60 else ''}'",
                    evidence=f"Found: {case_name}",
                ),
                ReasoningStep(
                    type="Jurisdictional Analysis",
                    description=f"Identified case from {court} decided {date_filed}",
                    evidence=f"Official citation: {citation_str}",
                ),
                ReasoningStep(
                    type="Content Relevance",
                    description="Analyzed case content for relevance to query",
                    evidence=f'Relevant excerpt: "{passage_preview}{"..." if len(passage_text) > 150 else ""}"'
                    if passage_text
                    else "Matched on case name and legal subject matter",
                ),
                ReasoningStep(
                    type="Precedential Value",
                    description=f"Ranked #{result.get('rank', i + 1)} among case law results based on relevance",
                    evidence=f"Key legal concepts: {', '.join(key_phrases[:4]) if key_phrases else 'General subject matter relevance'}",
                ),
            ],
            logic=CitationLogic(
                query_intent=f"Searching for case law precedent related to: {query[:80]}",
                matching_criteria=f"Court: {court} | Citation: {citation_str} | Date: {date_filed} | Relevance rank: #{result.get('rank', i + 1)}",
                application=f"This case from {court} may provide precedential guidance. The opinion discusses matters relevant to the query.",
            ),
            document_id=None,
            notes=f"CourtListener URL: {metadata.get('url', '')}",
            url=metadata.get("url", ""),
        )
        # Mark if this case was actually cited by the AI in its response
        if case_name.lower() in cited_case_names:
            citation.was_cited_by_ai = True
        citations.append(citation)

    return citations
