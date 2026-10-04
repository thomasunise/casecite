import { Icon } from './Icon';
import type { CaseInfo } from '../../types';
import { safeHttpUrl } from './safeUrl';

interface CaseOpinion {
  id?: number;
  type?: string;
  type_label?: string;
  author?: string | null;
  per_curiam?: boolean;
  text?: string;
}

interface CaseDetailViewProps {
  s: Record<string, string>;
  selectedCase: CaseInfo;
  caseLoading: boolean;
  setSelectedCase: (c: CaseInfo | null) => void;
}

function CaseDetailView({ s, selectedCase, caseLoading, setSelectedCase }: CaseDetailViewProps) {
  const opinions = (Array.isArray(selectedCase.opinions) ? selectedCase.opinions : []) as CaseOpinion[];
  const hasOpinions = opinions.some((o) => (o.text || '').trim());
  const docketNumber = selectedCase.docket_number ? String(selectedCase.docket_number) : null;
  const natureOfSuit = selectedCase.nature_of_suit ? String(selectedCase.nature_of_suit) : null;
  const status = selectedCase.precedential_status ? String(selectedCase.precedential_status) : null;
  const headnotes = selectedCase.headnotes ? String(selectedCase.headnotes) : null;
  const posture = selectedCase.posture ? String(selectedCase.posture) : null;
  const url = selectedCase.url ? String(selectedCase.url) : null;

  return (
    <div className={s.caseDetailView}>
      <button className={s.backToResultsBtn} onClick={() => setSelectedCase(null)}>
        <Icon name="ChevronLeft" size={14} /> Back to results
      </button>
      {caseLoading ? (
        <div className={s.caseLoading}>
          <Icon name="Loader2" size={20} className={s.spinner} />
          <span>Loading case...</span>
        </div>
      ) : selectedCase.error ? (
        <div className={s.toolErrorBox}>
          <Icon name="AlertCircle" size={14} />
          <span>{selectedCase.error}</span>
        </div>
      ) : (
        <>
          <h3 className={s.caseDetailTitle}>{selectedCase.case_name}</h3>
          <div className={s.caseDetailMeta}>
            {selectedCase.court && <span><Icon name="Building" size={12} /> {selectedCase.court}</span>}
            {selectedCase.date_filed && <span><Icon name="Calendar" size={12} /> {selectedCase.date_filed}</span>}
            {selectedCase.date_argued ? <span><Icon name="Mic" size={12} /> Argued {String(selectedCase.date_argued)}</span> : null}
            {docketNumber && <span><Icon name="Hash" size={12} /> {docketNumber}</span>}
            {(selectedCase.times_cited ?? 0) > 0 && <span><Icon name="Quote" size={12} /> Cited {selectedCase.times_cited!.toLocaleString()} times</span>}
            {status && <span><Icon name="BookOpen" size={12} /> {status}</span>}
          </div>
          {(selectedCase.citations?.length ?? 0) > 0 && (
            <div className={s.caseDetailCitations}>
              {selectedCase.citations!.map((cite: string | Record<string, unknown>, i: number) => (
                <span key={i} className={s.caseDetailCite}>
                  {typeof cite === 'string' ? cite : `${cite.volume || ''} ${cite.reporter || ''} ${cite.page || ''}`.trim() || 'Citation'}
                </span>
              ))}
            </div>
          )}
          {selectedCase.judges && (
            <div className={s.caseDetailJudges}>
              <strong>Judges:</strong> {selectedCase.judges}
            </div>
          )}
          {(natureOfSuit || posture) && (
            <div className={s.caseDetailJudges}>
              {natureOfSuit && <><strong>Nature of suit:</strong> {natureOfSuit}</>}
              {natureOfSuit && posture ? ' · ' : ''}
              {posture && <><strong>Posture:</strong> {posture}</>}
            </div>
          )}

          {selectedCase.syllabus && (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailSectionTitle}>Syllabus</div>
              <div className={s.caseDetailText}>{selectedCase.syllabus}</div>
            </div>
          )}
          {headnotes && (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailSectionTitle}>Headnotes</div>
              <div className={s.caseDetailText}>{headnotes}</div>
            </div>
          )}
          {hasOpinions ? (
            opinions.filter((o) => (o.text || '').trim()).map((o, i) => (
              <div key={o.id ?? i} className={s.caseDetailSection}>
                <div className={s.caseDetailSectionTitle}>
                  {o.type_label || 'Opinion'}
                  {o.per_curiam ? ' · per curiam' : o.author ? ` · ${o.author}` : ''}
                </div>
                <div className={s.caseOpinionText}>{o.text}</div>
              </div>
            ))
          ) : selectedCase.opinion_text ? (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailSectionTitle}>Opinion</div>
              <div className={s.caseOpinionText}>{selectedCase.opinion_text}</div>
            </div>
          ) : (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailText}>
                CourtListener has no opinion text for this case{url ? ' — open it on CourtListener for the scanned original.' : '.'}
              </div>
            </div>
          )}

          {url && (
            <a href={safeHttpUrl(url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.oralArgLink}>
              <Icon name="ExternalLink" size={12} /> View on CourtListener
            </a>
          )}
        </>
      )}
    </div>
  );
}

export { CaseDetailView };
