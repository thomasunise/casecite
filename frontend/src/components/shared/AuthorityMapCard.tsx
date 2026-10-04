import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import { mappingToCitation } from '../../utils';
import type { AuthorityMapChatResult, AuthorityMapping } from '../../api/types';
import type { Citation } from '../../types/research';
import s from './AuthorityMapCard.module.css';

interface AuthorityMapCardProps {
  result: AuthorityMapChatResult;
  onCitationSelect: (citation: Citation) => void;
}

/**
 * Chat-message card for an exhaustive authority map: every proposition found
 * in the scoped file(s) with its verified (or unverified) supporting case.
 * Clicking a row opens the standard citation verification popup — ids match
 * the citations pushed into the Sources panel (same sort, same prefix).
 */
function AuthorityMapCard({ result, onCitationSelect }: AuthorityMapCardProps) {
  const t = result.totals;
  return (
    <div className={s.card}>
      <div className={s.header}>
        <Icon name="ShieldCheck" size={15} className={s.headerIcon} />
        <span className={s.title}>Authority map</span>
        <span className={s.totals}>
          {t.verified} verified · {t.authorities} authorities · {t.propositions} propositions
          {t.files > 1 ? ` · ${t.files} files` : ''}
        </span>
      </div>
      {result.files.map((f, fi) => {
        const ordered = [...f.mappings].sort((a, b) => Number(b.verified) - Number(a.verified));
        return (
          <div key={f.run_id} className={s.fileBlock}>
            {result.files.length > 1 && (
              <div className={s.fileName}>
                <Icon name="FileText" size={13} />
                <span className={s.fileNameText}>{f.document_name || 'Document'}</span>
                <span className={s.fileCounts}>
                  {f.summary.verified ?? 0}/{f.summary.authorities ?? 0} verified
                </span>
              </div>
            )}
            {ordered.length === 0 && (
              <p className={s.empty}>No supporting authorities found for this file.</p>
            )}
            {ordered.map((m: AuthorityMapping, i: number) => (
              <button
                key={`${f.run_id}-${i}`}
                className={s.row}
                onClick={() => onCitationSelect(mappingToCitation(m, i, `am${fi}`))}
              >
                <span className={m.verified ? s.badgeVerified : s.badgeUnverified}>
                  <Icon name={m.verified ? 'ShieldCheck' : 'ShieldAlert'} size={11} />
                  {m.verified ? 'Verified' : 'Unverified'}
                </span>
                <span className={s.rowBody}>
                  <span className={s.proposition}>{m.proposition}</span>
                  <span className={s.caseName}>
                    {m.case_name || m.citation || 'Authority'}
                    {m.citation && m.case_name ? ` — ${m.citation}` : ''}
                  </span>
                </span>
                <Icon name="ChevronRight" size={13} className={s.chevron} />
              </button>
            ))}
          </div>
        );
      })}
      {(result.coverage_notes?.length ?? 0) > 0 && (
        <div className={s.coverage} role="note">
          <Icon name="AlertCircle" size={12} className={s.coverageIcon} />
          <div>
            Not every file was covered in full:
            <ul className={s.coverageList}>
              {result.coverage_notes?.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          </div>
        </div>
      )}
      <AiNotice />
    </div>
  );
}

export { AuthorityMapCard };
