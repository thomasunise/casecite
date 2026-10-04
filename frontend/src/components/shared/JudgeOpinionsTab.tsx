import React from 'react';
import { Icon } from './Icon';
import { activateOnKey } from './activateOnKey';
import { safeHttpUrl } from './safeUrl';
import type { OpinionSummary, OpinionListResponse } from '../../types';
import type { JudgeOpinionSort } from '../../stores/judgeIntelStore';

interface JudgeOpinionsTabProps {
  s: Record<string, string>;
  judgeId: string;
  selectedOpinion: OpinionSummary | null;
  setSelectedOpinion: (opinion: OpinionSummary | null) => void;
  loadOpinionFullText: (judgeId: string, opinionId: string) => void;
  judgeIntelOpinionQuery: string;
  setJudgeIntelOpinionQuery: (value: string) => void;
  judgeIntelOpinionSort: JudgeOpinionSort;
  queryJudgeOpinions: (judgeId: string, query?: string, offset?: number, sort?: JudgeOpinionSort) => void;
  judgeIntelLoading: boolean;
  judgeIntelOpinions: OpinionListResponse | null;
}

function JudgeOpinionsTab({
  s,
  judgeId,
  selectedOpinion,
  setSelectedOpinion,
  loadOpinionFullText,
  judgeIntelOpinionQuery,
  setJudgeIntelOpinionQuery,
  judgeIntelOpinionSort,
  queryJudgeOpinions,
  judgeIntelLoading,
  judgeIntelOpinions,
}: JudgeOpinionsTabProps) {
  return (
    <div className={s.judgeProfileSection}>
      <h3 className={s.judgeProfileSectionTitle}>Opinions</h3>
      {selectedOpinion ? (
        <div className={s.opinionFullView}>
          <button className={s.backToResultsBtn} onClick={() => setSelectedOpinion(null)}>
            <Icon name="ChevronLeft" size={14} /> Back to opinions
          </button>
          <h3 className={s.opinionFullTitle}>{selectedOpinion.case_name}</h3>
          <div className={s.opinionFullMeta}>
            {selectedOpinion.court && <span>{selectedOpinion.court}</span>}
            {selectedOpinion.date_filed && <span>{selectedOpinion.date_filed}</span>}
            {selectedOpinion.citation && <span className="mono">{selectedOpinion.citation}</span>}
            {selectedOpinion.docket_number ? <span>No. {String(selectedOpinion.docket_number)}</span> : null}
            {(selectedOpinion.citation_count ?? 0) > 0 && <span>{selectedOpinion.citation_count} citations</span>}
            {safeHttpUrl(selectedOpinion.url) && (
              <a href={safeHttpUrl(selectedOpinion.url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.wikiLink}>
                <Icon name="ExternalLink" size={11} className={s.wikiLinkIcon} />CourtListener
              </a>
            )}
          </div>
          {selectedOpinion.full_text ? (
            <div className={s.opinionFullText}>{selectedOpinion.full_text}</div>
          ) : (
            <div className={s.opinionFullText}>
              CourtListener has no text for this opinion in its database
              {selectedOpinion.url ? ' — the scanned original may be available on the CourtListener page linked above.' : '.'}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className={s.opinionSearchBox}>
            <input
              type="text"
              className={s.opinionSearchInput}
              placeholder="Search opinions (case name, text)..."
              aria-label="Search opinions"
              value={judgeIntelOpinionQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setJudgeIntelOpinionQuery(e.target.value)}
              onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && queryJudgeOpinions(judgeId, judgeIntelOpinionQuery)}
            />
            <button
              className={s.opinionSearchBtn}
              onClick={() => queryJudgeOpinions(judgeId, judgeIntelOpinionQuery)}
              aria-label="Search opinions"
            >
              <Icon name="Search" size={14} />
            </button>
          </div>

          <div className={s.scopeRow}>
            <span className={s.scopeLabel}>Sort by</span>
            <button
              className={`${s.scopePill} ${judgeIntelOpinionSort === 'citations' ? s.scopePillActive : ''}`}
              onClick={() => queryJudgeOpinions(judgeId, judgeIntelOpinionQuery, 0, 'citations')}
            >
              Most Cited
            </button>
            <button
              className={`${s.scopePill} ${judgeIntelOpinionSort === 'date' ? s.scopePillActive : ''}`}
              onClick={() => queryJudgeOpinions(judgeId, judgeIntelOpinionQuery, 0, 'date')}
            >
              Newest
            </button>
          </div>

          {judgeIntelLoading && (
            <div className={s.caseLoading}><Icon name="Loader2" size={20} className={s.spinnerIcon} /> Loading opinions...</div>
          )}

          {judgeIntelOpinions && (
            <>
              <div className={s.opinionResultsHeader}>{judgeIntelOpinions.total?.toLocaleString()} opinions</div>
              <div className={s.opinionResultsList}>
                {judgeIntelOpinions.opinions?.map((op: OpinionSummary, i: number) => (
                  <div
                    key={`${op.id}-${i}`}
                    className={s.opinionResultItem}
                    role="button"
                    tabIndex={0}
                    onClick={() => loadOpinionFullText(judgeId, op.id)}
                    onKeyDown={activateOnKey(() => loadOpinionFullText(judgeId, op.id))}
                  >
                    <div className={s.judgeProfileItemRow}>
                      <div className={s.opinionResultName}>{op.case_name}</div>
                      {safeHttpUrl(op.url) && (
                        <a
                          href={safeHttpUrl(op.url) ?? undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={s.judgeProfileItemLink}
                          title="View on CourtListener"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Icon name="ExternalLink" size={12} />
                        </a>
                      )}
                    </div>
                    <div className={s.opinionResultMeta}>
                      {op.citation && <span className="mono">{op.citation}</span>}
                      {op.court && <span>{op.court}</span>}
                      {op.date_filed && <span>{op.date_filed}</span>}
                      {op.docket_number ? <span>No. {String(op.docket_number)}</span> : null}
                      {(op.citation_count ?? 0) > 0 && <span>{op.citation_count} citations</span>}
                    </div>
                    {op.snippet && <div className={s.opinionResultSnippet}>{op.snippet}...</div>}
                  </div>
                ))}
              </div>
              {(judgeIntelOpinions.opinions?.length ?? 0) < (judgeIntelOpinions.total ?? 0) && (
                <button
                  className={s.loadMoreBtn}
                  onClick={() => queryJudgeOpinions(judgeId, judgeIntelOpinionQuery, judgeIntelOpinions.opinions?.length ?? 0)}
                  disabled={judgeIntelLoading}
                >
                  Load More ({judgeIntelOpinions.opinions?.length ?? 0} of {judgeIntelOpinions.total?.toLocaleString()})
                </button>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

export { JudgeOpinionsTab };
export default JudgeOpinionsTab;
