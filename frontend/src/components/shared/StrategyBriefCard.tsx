import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import { CaseLawRemovedNotice } from './CaseLawRemovedNotice';
import { useCaseViewStore } from '../../stores/caseViewStore';
import type { StrategyBriefResponse, StrategyBriefPoint } from '../../api/types';
import type { Citation } from '../../types';
import { safeHttpUrl } from './safeUrl';

interface StrategyBriefCardProps {
  brief: StrategyBriefResponse;
  citations: Citation[];
  onCitationClick: (cite: Citation) => void;
  s: Record<string, string>;
}

/** Honest one-sentence account of why the case-law stage attached nothing —
 * built from the backend's per-reason drop counters, never guessed. */
function caseLawOutcome(cl: NonNullable<StrategyBriefResponse['case_law']>): string {
  if (cl.timed_out) {
    return 'The case-law search ran out of time before finishing — try again, or run Case Citations on a specific filing.';
  }
  const points = `${cl.points_searched} point${cl.points_searched === 1 ? '' : 's'}`;
  if (!cl.opinions_read) {
    if (cl.searches_failed) {
      const detail = cl.search_error ? ` (${cl.search_error})` : '';
      return `Case law was searched for ${points}, but the case-law search service could not be reached${detail}. Try again in a moment.`;
    }
    if (cl.unreadable) {
      return `Case law was searched for ${points}, but none of the candidate opinions could be retrieved in readable form.`;
    }
    return `Case law was searched for ${points}, but no candidate opinions were found. Try Case Citations on a specific filing for a deeper hunt.`;
  }
  const reasons: string[] = [];
  if (cl.unsupportive) {
    reasons.push(`${cl.unsupportive} did not support the points on our side`);
  }
  if (cl.quote_unverified) {
    reasons.push(
      `${cl.quote_unverified} offered no quote that verified verbatim against the real opinion text`
    );
  }
  if (cl.unreadable) reasons.push(`${cl.unreadable} could not be retrieved in readable form`);
  if (cl.errors) reasons.push(`${cl.errors} hit errors while being judged`);
  const partial = cl.partially_read ?? 0;
  const read = partial > 0
    ? `${cl.opinions_read} opinion${cl.opinions_read === 1 ? ' was' : 's were'} read (${partial} only in part — too long to read in full)`
    : `${cl.opinions_read} opinion${cl.opinions_read === 1 ? ' was' : 's were'} read in full`;
  const why = reasons.length ? `: ${reasons.join('; ')}` : ', but none survived review';
  return `Case law was searched for ${points} and ${read}${why}. Only verified authorities are ever shown — try Case Citations on a specific filing for a deeper hunt.`;
}

/** Structured matter-strategy brief rendered inside the chat thread:
 * position, strengths, weaknesses, and next steps — every point carrying
 * clickable citations back to the underlying documents. */
function StrategyBriefCard({ brief, citations, onCitationClick, s }: StrategyBriefCardProps) {
  const byId = new Map(citations.map((c) => [c.id, c]));
  const { loadCaseDetail } = useCaseViewStore();
  const authoritiesById = new Map(
    (brief.citations || []).filter((c) => c.type === 'case_law').map((c) => [c.id, c])
  );

  const renderPoints = (title: string, points: StrategyBriefPoint[]) => {
    if (!points?.length) return null;
    return (
      <div className={s.briefSection}>
        <div className={s.briefSectionTitle}>{title}</div>
        {points.map((p, i) => (
          <div key={i} className={s.briefPoint}>
            <span className={`${s.briefPointNum} mono`}>{i + 1}.</span>
            <div className={s.briefPointBody}>
              <p className={s.briefPointText}>{p.point || p.step}</p>
              {(p.citation_ids?.length ?? 0) > 0 && (
                <div className={s.briefCites}>
                  {p.citation_ids.map((id) => {
                    const cite = byId.get(id);
                    if (!cite) return null;
                    return (
                      <button key={id} className={s.briefCiteChip} onClick={() => onCitationClick(cite)}>
                        <Icon name={cite.type === 'case_law' ? 'Scale' : 'FileText'} size={10} />
                        {cite.source}
                      </button>
                    );
                  })}
                </div>
              )}
              {(p.case_refs?.length ?? 0) > 0 && (
                <div className={s.briefAuthorities}>
                  {p.case_refs?.map((id) => {
                    const auth = authoritiesById.get(id);
                    if (!auth) return null;
                    return (
                      <div key={id} className={s.briefAuthority}>
                        <div className={s.briefAuthorityHead}>
                          <Icon name="Scale" size={11} />
                          {auth.opinionId ? (
                            <button
                              className={s.briefAuthorityNameBtn}
                              title="Read the full opinion"
                              onClick={() => loadCaseDetail(auth.opinionId as string)}
                            >
                              {auth.source}
                            </button>
                          ) : (
                            <span className={s.briefAuthorityName}>{auth.source}</span>
                          )}
                          {auth.reference && (
                            <span className={`${s.briefAuthorityCite} mono`}>{auth.reference}</span>
                          )}
                          {auth.verified && (
                            <span className={s.briefAuthorityVerified}>
                              <Icon name="ShieldCheck" size={11} /> quote verified
                            </span>
                          )}
                          {auth.url && (
                            <a
                              className={s.briefAuthorityLink}
                              href={safeHttpUrl(auth.url) ?? undefined}
                              target="_blank"
                              rel="noreferrer"
                            >
                              CourtListener <Icon name="ExternalLink" size={10} />
                            </a>
                          )}
                        </div>
                        {auth.passage && (
                          <blockquote className={s.briefAuthorityQuote}>“{auth.passage}”</blockquote>
                        )}
                        {auth.explanation && <p className={s.briefAuthorityHow}>{auth.explanation}</p>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className={s.briefCard}>
      <div className={s.briefOverline}>
        Strategy brief · {brief.scope?.documents_considered ?? 0} document{(brief.scope?.documents_considered ?? 0) === 1 ? '' : 's'} reviewed
        {brief.scope?.documents_total > brief.scope?.documents_considered && (
          <span className={s.briefTruncNote}> (of {brief.scope.documents_total})</span>
        )}
      </div>
      {brief.scope?.coverage_note && (
        <div className={s.briefCoverageNote}>{brief.scope.coverage_note}</div>
      )}
      <p className={s.briefPosition}>{brief.position}</p>
      {renderPoints('Strengths', brief.strengths)}
      {renderPoints('Weaknesses & Exposure', brief.weaknesses)}
      {renderPoints('Recommended Next Steps', brief.next_steps)}
      {brief.case_law?.requested && brief.case_law.attached === 0 && (
        <div className={s.briefCaseLawNote}>
          <Icon name="Scale" size={12} /> {caseLawOutcome(brief.case_law)}
        </div>
      )}
      {brief.case_law?.requested && brief.case_law.attached > 0 && (brief.case_law.partially_read ?? 0) > 0 && (
        <div className={s.briefCaseLawNote}>
          <Icon name="Scale" size={12} /> {brief.case_law.partially_read} of the opinions considered {brief.case_law.partially_read === 1 ? 'was' : 'were'} too long to read in full; only the opening portion was reviewed.
        </div>
      )}
      <CaseLawRemovedNotice removed={brief.case_law_removed} className={s.briefCaseLawNote} />
      <AiNotice />
    </div>
  );
}

export { StrategyBriefCard };
