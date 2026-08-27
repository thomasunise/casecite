import { Icon } from './Icon';
import { activateOnKey } from './activateOnKey';
import { safeHttpUrl } from './safeUrl';
import { groupCitationsBySource, claimLabel } from '../../utils';
import type { Citation } from '../../types';

interface SourcesListProps {
  s: Record<string, string>;
  allCitations: Citation[];
  setSelectedCitation: (cite: Citation) => void;
  /** Hide the built-in heading when rendered inside a categorized section. */
  showTitle?: boolean;
  /** Citation currently hovered in the chat's numbered pills — spotlit here. */
  hoveredCitationId?: string | null;
}

function SourcesList({ s, allCitations, setSelectedCitation, showTitle = true, hoveredCitationId }: SourcesListProps) {
  const groups = groupCitationsBySource(allCitations);
  return (
    <div className={s.rightSection}>
      {showTitle && <h4 className={s.rightSectionTitle}>Sources ({groups.length})</h4>}
      {groups.length === 0 ? (
        <div className={s.emptyPanel}>
          <Icon name="FileSearch" size={24} className={s.emptyPanelIcon} />
          <div>No sources yet</div>
          <div className={s.emptyPanelDesc}>
            Run a search to see cited sources
          </div>
        </div>
      ) : (
        <div className={s.sourcesList}>
          {groups.map(({ top: cite, count }, rowIndex) => {
            // Extract URL from notes if not in url field
            const sourceUrl = safeHttpUrl(cite.url || (cite.notes?.match(/https?:\/\/[^\s]+/)?.[0]));
            // A claim citation IS one fact of the answer — its row says the
            // fact; the filename is the meta line.
            const claim = claimLabel(cite);
            return (
              <div
                key={cite.id}
                className={`${s.sourceItem} ${hoveredCitationId === cite.id ? s.sourceItemHot : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedCitation(cite)}
                onKeyDown={activateOnKey(() => setSelectedCitation(cite))}
              >
                <span className={s.sourceNum}>{rowIndex + 1}</span>
                <div className={s.sourceContent}>
                  <span className={s.sourceName}>{claim || cite.source}</span>
                  <span className={s.sourceMeta}>
                    <span>{claim ? cite.source : (cite.type === 'case_law' ? 'Case Law' : 'Internal Doc')}</span>
                    {/* The ONLY quality signal is binary verification — never
                        a score or a match-strength gradient. */}
                    {cite.verified === true && (
                      <>
                        <span className={s.sourceMetaRule} aria-hidden="true" />
                        <span className={s.verifiedBadge}>Verified</span>
                      </>
                    )}
                    {cite.verified === false && (
                      <>
                        <span className={s.sourceMetaRule} aria-hidden="true" />
                        <span className={s.unverifiedBadge}>Unverified</span>
                      </>
                    )}
                    {count > 1 && (
                      <>
                        <span className={s.sourceMetaRule} aria-hidden="true" />
                        <span>{count} passages</span>
                      </>
                    )}
                    {cite.was_cited_by_ai && (
                      <>
                        <span className={s.sourceMetaRule} aria-hidden="true" />
                        <span className={s.sourceCited}>
                          <Icon name="Check" size={10} /> Cited
                        </span>
                      </>
                    )}
                  </span>
                </div>
                {sourceUrl && (
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className={s.sourceLink} onClick={e => e.stopPropagation()}>
                    <Icon name="ExternalLink" size={12} />
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export { SourcesList };
