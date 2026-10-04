import type { AuthorityMapCoverage, AuthorityMapping } from '../api/types';
import type { Citation } from '../types/research';
import type { DocAnnotation } from '../components/shared/AnnotatedDocument';

/**
 * Map an authority-mapper result row into the app-wide Citation shape so it
 * flows through the Sources panel and the citation verification popup exactly
 * like any other case-law citation.
 *
 * `idPrefix` keeps ids unique when mappings from several files land in one
 * conversation (the chat authority map runs across a whole folder).
 */
export function mappingToCitation(m: AuthorityMapping, i: number, idPrefix = 'am'): Citation {
  const steps = (m.reasoning?.steps ?? [])
    .filter((step) => (step?.description ?? '').trim())
    .map((step) => ({
      type: step.type || 'Analysis',
      description: step.description as string,
      evidence: step.evidence ?? null,
    }));
  return {
    id: `${idPrefix}-${m.id ?? i}-${m.source_ref ?? i}`,
    source: m.case_name || m.citation || 'Authority',
    type: 'case_law',
    confidence: Math.round((m.relevance ?? 0) * 100),
    status: 'pending',
    similarity: m.relevance ?? 0,
    relevanceRank: i + 1,
    chunkIndex: 0,
    tokenCount: 0,
    passage: m.support_quote || '',
    reference: m.citation || undefined,
    reasoning: steps,
    logic: {
      queryIntent: m.proposition,
      matchingCriteria: m.verified
        ? 'Supporting passage verified verbatim in the source opinion'
        : 'Unverified — supporting passage could not be located verbatim in the source',
      application: m.reasoning?.application || '',
    },
    notes: '',
    reviewedAt: null,
    document_id: null,
    url: m.source_url || null,
    was_cited_by_ai: true,
    opinionId: m.source_ref ?? null,
    verified: m.verified,
  };
}

/**
 * One plain sentence saying what an authority-map run did NOT cover, built
 * from the server's coverage counters (same wording as the chat job's
 * `coverage_notes`). Null when the run covered everything.
 */
export function authorityMapCoverageNote(coverage?: AuthorityMapCoverage | null): string | null {
  if (!coverage) return null;
  const gaps: string[] = [];
  if (coverage.document_truncated) {
    gaps.push(
      `${(coverage.document_chars_read ?? 0).toLocaleString()} of ${(coverage.document_chars ?? 0).toLocaleString()} characters were read`
    );
  }
  if (coverage.document_windows_failed) {
    gaps.push(`${coverage.document_windows_failed} section(s) could not be analysed`);
  }
  const identified = coverage.propositions_identified ?? 0;
  const researched = coverage.propositions_researched ?? 0;
  if (identified > researched) {
    gaps.push(`${researched} of ${identified} propositions were researched`);
  }
  if (coverage.opinions_partially_read) {
    gaps.push(`${coverage.opinions_partially_read} opinion(s) were only partly read`);
  }
  return gaps.length ? `Not covered in full: ${gaps.join('; ')}.` : null;
}

/**
 * Group mappings that annotate the same character span of the document into
 * one DocAnnotation, dropping mappings without a resolved span. Derived once
 * when a result lands (store state), not on every render.
 */
export function buildDocAnnotations(mappings: AuthorityMapping[]): DocAnnotation[] {
  const byKey = new Map<string, DocAnnotation>();
  for (const m of mappings) {
    if (m.doc_span_start == null || m.doc_span_end == null) continue;
    const key = `${m.doc_span_start}:${m.doc_span_end}`;
    if (!byKey.has(key)) byKey.set(key, { start: m.doc_span_start, end: m.doc_span_end, mappings: [] });
    byKey.get(key)!.mappings.push(m);
  }
  return [...byKey.values()];
}
