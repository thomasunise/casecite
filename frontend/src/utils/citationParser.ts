import { generateId } from './index';
import type { Citation, ReasoningStep } from '../types';

/**
 * Parse raw citation data from the RAG API response into typed Citation objects.
 *
 * Reasoning/logic fields are populated only from what the backend actually
 * produced — never with invented placeholder text. `query` (when provided)
 * becomes the citation's query intent so the reasoning modal can show what
 * the source was matched against.
 */
export function parseCitations(rawCitations: unknown[], query?: string): Citation[] {
  return (rawCitations as Record<string, unknown>[]).map((cite, idx) => {
    const type = (cite.type as string) || 'document';
    return {
      id: (cite.id as string) || generateId(),
      source: (cite.source as string) || `Source ${idx + 1}`,
      type,
      confidence: Math.min(100, Math.round((cite.confidence as number) > 1 ? (cite.confidence as number) : ((cite.confidence as number) || 0.8) * 100)),
      status: (cite.status as Citation['status']) || 'pending',
      similarity: (cite.similarity as number) || 0.8,
      relevanceRank: (cite.relevance_rank as number) || idx + 1,
      chunkIndex: (cite.chunk_index as number) || idx,
      tokenCount: (cite.token_count as number) || 0,
      passage: (cite.passage as string) || '',
      caseSummary: (cite.case_summary as string) || null,
      reasoning: ((cite.reasoning as Record<string, unknown>[]) || []).map((r): ReasoningStep => ({
        type: (r.type as string) || 'Analysis',
        description: r.description as string,
        evidence: (r.evidence as string) || '',
      })).filter((r) => (r.description ?? '').trim()),
      logic: {
        // Prefer what the backend actually determined (claim grounding writes
        // real verification language here); fall back to generic provenance.
        queryIntent: ((cite.logic as Record<string, unknown>)?.query_intent as string) || query || '',
        matchingCriteria: ((cite.logic as Record<string, unknown>)?.matching_criteria as string)
          || (type === 'case_law'
            ? 'Retrieved from CourtListener case law'
            : 'Semantic match from your documents'),
        application: ((cite.logic as Record<string, unknown>)?.application as string)
          || (cite.application as string) || '',
      },
      notes: '',
      reviewedAt: null,
      document_id: (cite.document_id as string) || null,
      url: (cite.url as string) || null,
      opinionId: (cite.opinion_id as string) || (cite.opinionId as string) || null,
      verified: typeof cite.verified === 'boolean' ? (cite.verified as boolean) : undefined,
      docSpanStart: (cite.doc_span_start as number) ?? null,
      docSpanEnd: (cite.doc_span_end as number) ?? null,
    };
  });
}
