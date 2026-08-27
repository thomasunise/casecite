import type { Citation } from '../types';

/* Relevance scores, ranks, and match-strength tiers are deliberately never
   shown to the user: retrieval telemetry is not a legal judgment, and any
   gradient ("strong match" vs "relevant") plants doubt about every citation
   below the top tier. The only quality signal in the UI is binary
   verification — the quote is verbatim in its source, or it is flagged. */

export interface SourceGroup {
  /** Highest-confidence citation of the group — used for click-through and tier. */
  top: Citation;
  /** Number of passages this source contributed. */
  count: number;
}

/** A claim-grounded citation stands for ONE fact of the answer (with its own
    verified quote + span), not a retrieval chunk. */
const CLAIM_STEP_TYPES = new Set(['Fact in the answer', 'From the answer']);

function isClaimCitation(cite: Citation): boolean {
  return cite.docSpanStart != null || CLAIM_STEP_TYPES.has(cite.reasoning?.[0]?.type ?? '');
}

/** The fact this citation supports, for use as its row label. */
export function claimLabel(cite: Citation): string | null {
  if (!isClaimCitation(cite)) return null;
  const first = cite.reasoning?.[0];
  if (first && CLAIM_STEP_TYPES.has(first.type) && first.description?.trim()) {
    return first.description.trim();
  }
  if (cite.logic?.application?.trim()) return cite.logic.application.trim();
  return cite.passage ? cite.passage.slice(0, 90) : null;
}

/**
 * Collapse per-chunk citations into one entry per source document — seven rows
 * of "Faith Group Proposal.pdf" is chunk plumbing, not information. But
 * claim-grounded citations are per-FACT: each one is a distinct verifiable
 * point of the answer and must NEVER be collapsed behind a filename.
 */
export function groupCitationsBySource(citations: Citation[]): SourceGroup[] {
  const groups = new Map<string, SourceGroup>();
  for (const cite of citations) {
    const key = isClaimCitation(cite) ? `claim::${cite.id}` : `${cite.type}::${cite.source}`;
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, { top: cite, count: 1 });
    } else {
      existing.count += 1;
      if ((cite.confidence ?? 0) > (existing.top.confidence ?? 0)) {
        existing.top = cite;
      }
    }
  }
  // Claim citations keep the answer's order (rank); chunk groups sort by
  // confidence after them.
  return [...groups.values()].sort((a, b) => {
    const aClaim = isClaimCitation(a.top);
    const bClaim = isClaimCitation(b.top);
    if (aClaim !== bClaim) return aClaim ? -1 : 1;
    if (aClaim && bClaim) return (a.top.relevanceRank ?? 0) - (b.top.relevanceRank ?? 0);
    return (b.top.confidence ?? 0) - (a.top.confidence ?? 0);
  });
}
