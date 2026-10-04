import { Icon } from './Icon';
import { activateOnKey } from './activateOnKey';
import { safeHttpUrl } from './safeUrl';
import type { ToolResultData } from './ToolResultsArea';

interface CaseSearchResultsProps {
  s: Record<string, string>;
  tr: ToolResultData;
  toolLoading: boolean;
  loadCaseDetail: (id: string) => void;
  loadMoreResults: () => void;
}

function CaseSearchResults({ s, tr, toolLoading, loadCaseDetail, loadMoreResults }: CaseSearchResultsProps) {
  return (
    <div className={`${s.toolCard} ${s.caseSearchResults}`}>
      <div className={s.toolOverline}>Case Lookup · CourtListener</div>
      <div className={s.searchResultsHeader}>
        <span>{tr.count?.toLocaleString() || 0} cases found</span>
        <span className={s.searchResultsPage}>Showing {tr.results?.length || 0}</span>
      </div>
      <div className={s.caseResultsList}>
        {tr.results!.map((c, i) => {
          const citations = Array.isArray(c.citation) ? (c.citation as string[]) : c.citation ? [String(c.citation)] : [];
          const status = typeof c.status === 'string' ? c.status : null;
          const url = safeHttpUrl(c.url);
          return (
            <div
              key={`${c.id}-${i}`}
              className={`case-result ${s.caseResultItem}`}
              role="button"
              tabIndex={0}
              onClick={() => loadCaseDetail(c.id)}
              onKeyDown={activateOnKey(() => loadCaseDetail(c.id))}
              style={{ cursor: 'pointer' }}
            >
              <div className={s.caseResultContent}>
                <div className={s.caseResultName}>{c.case_name}</div>
                <div className={s.caseResultMeta}>
                  {c.court && <span>{c.court}</span>}
                  {c.date_filed && <span>{c.date_filed}</span>}
                  {c.docket_number ? <span>No. {String(c.docket_number)}</span> : null}
                  {(c.times_cited ?? 0) > 0 && <span>{c.times_cited!.toLocaleString()} citations</span>}
                  {status && status !== 'Published' && <span>{status}</span>}
                </div>
                {citations.length > 0 && (
                  <div className={s.caseResultCitation}>{citations.join(' · ')}</div>
                )}
                {c.judges ? <div className={s.caseResultMeta}><span>{c.judges}</span></div> : null}
                {c.snippet ? <div className={s.resultSnippet}>{String(c.snippet)}</div> : null}
              </div>
              {url ? (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  title="View on CourtListener"
                  className={s.caseResultLink}
                >
                  <Icon name="ExternalLink" size={14} className={s.resultRowLinkIcon} />
                </a>
              ) : null}
            </div>
          );
        })}
      </div>
      {tr.has_next && (
        <button
          className={s.loadMoreBtn}
          onClick={loadMoreResults}
          disabled={toolLoading}
        >
          {toolLoading ? 'Loading...' : `Load More (${tr.results!.length} of ${tr.count?.toLocaleString()})`}
        </button>
      )}
    </div>
  );
}

export { CaseSearchResults };
