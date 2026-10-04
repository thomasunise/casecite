import { Icon } from './Icon';
import { safeHttpUrl } from './safeUrl';

interface DocketDocument {
  description?: string;
  document_number?: string | number | null;
  page_count?: number | null;
  url?: string | null;
  is_available?: boolean;
}

interface DocketEntry {
  entry_number?: number | null;
  date_filed?: string | null;
  description?: string;
  documents?: DocketDocument[];
}

interface DocketParty {
  name?: string | null;
  role?: string | null;
  attorneys?: string[];
}

export interface DocketDetail {
  error?: string;
  id?: number;
  case_name?: string;
  case_name_full?: string | null;
  docket_number?: string;
  court?: string;
  court_name?: string | null;
  date_filed?: string | null;
  date_terminated?: string | null;
  date_last_filing?: string | null;
  date_argued?: string | null;
  assigned_to?: string | null;
  referred_to?: string | null;
  nature_of_suit?: string | null;
  cause?: string | null;
  jury_demand?: string | null;
  jurisdiction_type?: string | null;
  pacer_case_id?: string | null;
  entries?: DocketEntry[];
  entry_count?: number;
  parties?: DocketParty[];
  url?: string;
  [key: string]: unknown;
}

interface DocketDetailViewProps {
  s: Record<string, string>;
  docket: DocketDetail | null;
  docketLoading: boolean;
  onBack: () => void;
}

function DocketDetailView({ s, docket, docketLoading, onBack }: DocketDetailViewProps) {
  return (
    <div className={s.caseDetailView}>
      <button className={s.backToResultsBtn} onClick={onBack}>
        <Icon name="ChevronLeft" size={14} /> Back to results
      </button>
      {docketLoading ? (
        <div className={s.caseLoading}>
          <Icon name="Loader2" size={20} className={s.spinner} />
          <span>Loading docket...</span>
        </div>
      ) : !docket ? null : docket.error ? (
        <div className={s.toolErrorBox}>
          <Icon name="AlertCircle" size={14} />
          <span>{docket.error}</span>
        </div>
      ) : (
        <>
          <h3 className={s.caseDetailTitle}>{docket.case_name}</h3>
          {docket.case_name_full && docket.case_name_full !== docket.case_name && (
            <div className={s.caseDetailJudges}>{docket.case_name_full}</div>
          )}
          <div className={s.caseDetailMeta}>
            {(docket.court_name || docket.court) && (
              <span><Icon name="Building" size={12} /> {docket.court_name || docket.court!.toUpperCase()}</span>
            )}
            {docket.docket_number && <span><Icon name="Hash" size={12} /> {docket.docket_number}</span>}
            {docket.date_filed && <span><Icon name="Calendar" size={12} /> Filed {docket.date_filed}</span>}
            {docket.date_argued && <span><Icon name="Mic" size={12} /> Argued {docket.date_argued}</span>}
            {docket.date_terminated && <span><Icon name="CalendarX" size={12} /> Terminated {docket.date_terminated}</span>}
            {docket.date_last_filing && <span><Icon name="Clock" size={12} /> Last filing {docket.date_last_filing}</span>}
          </div>
          {(docket.assigned_to || docket.referred_to) && (
            <div className={s.caseDetailJudges}>
              {docket.assigned_to && <><strong>Assigned to:</strong> {docket.assigned_to}</>}
              {docket.assigned_to && docket.referred_to ? ' · ' : ''}
              {docket.referred_to && <><strong>Referred to:</strong> {docket.referred_to}</>}
            </div>
          )}
          {(docket.nature_of_suit || docket.cause || docket.jury_demand || docket.jurisdiction_type || docket.pacer_case_id) && (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailSectionTitle}>Case Information</div>
              <div className={s.caseDetailText}>
                {docket.nature_of_suit && <div>Nature of suit: {docket.nature_of_suit}</div>}
                {docket.cause && <div>Cause: {docket.cause}</div>}
                {docket.jury_demand && <div>Jury demand: {docket.jury_demand}</div>}
                {docket.jurisdiction_type && <div>Jurisdiction: {docket.jurisdiction_type}</div>}
                {docket.pacer_case_id && <div>PACER case ID: {docket.pacer_case_id}</div>}
              </div>
            </div>
          )}

          {(docket.parties?.length ?? 0) > 0 && (
            <div className={s.caseDetailSection}>
              <div className={s.caseDetailSectionTitle}>Parties ({docket.parties!.length})</div>
              {docket.parties!.map((p, i) => (
                <div key={i} className={s.resultRow}>
                  <div className={s.resultRowContent}>
                    <span className={s.resultRowTitle}>{p.name}</span>
                    <span className={s.resultRowMeta}>
                      {p.role || 'Party'}
                      {(p.attorneys?.length ?? 0) > 0 ? ` • Represented by ${p.attorneys!.join(', ')}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className={s.caseDetailSection}>
            <div className={s.caseDetailSectionTitle}>
              Filing Entries{docket.entry_count ? ` (${docket.entry_count})` : ''}
            </div>
            {(docket.entries?.length ?? 0) > 0 ? (
              docket.entries!.map((e, i) => {
                const docs = (e.documents || []).filter((d) => d.url && d.is_available !== false);
                return (
                  <div key={i} className={s.resultRow}>
                    {e.entry_number != null && <span className={s.resultRank}>{e.entry_number}</span>}
                    <div className={s.resultRowContent}>
                      <span className={s.resultRowTitle}>{e.description || 'No description available'}</span>
                      {e.date_filed && <span className={s.resultRowMeta}>{e.date_filed}</span>}
                      {docs.length > 0 && (
                        <span className={s.resultRowMeta}>
                          {docs.map((d, j) => (
                            <a key={j} href={safeHttpUrl(d.url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.oralArgLink}>
                              <Icon name="FileText" size={11} /> {d.description || `Document ${d.document_number ?? j + 1}`}
                              {d.page_count ? ` (${d.page_count} pp.)` : ''}
                            </a>
                          ))}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            ) : (
              <div className={s.caseDetailText}>
                No filing entries are available for this docket in the public archive.
                Entries appear when RECAP has collected them from PACER.
              </div>
            )}
            {docket.entry_count && docket.entries && docket.entry_count > docket.entries.length ? (
              <div className={s.caseDetailText}>
                Showing the {docket.entries.length} most recent of {docket.entry_count} entries — the full docket is on CourtListener.
              </div>
            ) : null}
          </div>

          {docket.url && (
            <a href={safeHttpUrl(docket.url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.oralArgLink}>
              <Icon name="ExternalLink" size={12} /> View on CourtListener
            </a>
          )}
        </>
      )}
    </div>
  );
}

export { DocketDetailView };
