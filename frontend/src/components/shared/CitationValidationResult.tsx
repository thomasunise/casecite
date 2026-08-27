import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import type { ToolResultData, CitingCase } from './ToolResultsArea';

interface CitationValidationResultProps {
  s: Record<string, string>;
  tr: ToolResultData;
}

const TREATMENT_LABEL: Record<string, string> = {
  negative: 'Negative language',
  caution: 'Cautionary language',
  positive: 'Positive language',
  neutral: 'Cited',
};

// What the scan found, stated as what it is: language in citing opinions,
// not an editorial judgment that the case is or is not good law.
const BADGE: Record<string, { icon: string; label: string; className: string }> = {
  none: { icon: 'CheckCircle', label: 'No negative language found', className: 'validationBadgeNone' },
  caution: { icon: 'AlertCircle', label: 'Cautionary language found', className: 'validationBadgeCaution' },
  warning: { icon: 'AlertTriangle', label: 'Negative language found — read before relying', className: 'validationBadgeWarning' },
  danger: { icon: 'AlertTriangle', label: 'Repeated negative language — likely bad law, verify', className: 'validationBadgeDanger' },
  unknown: { icon: 'HelpCircle', label: 'No treatment signal available', className: 'validationBadgeUnknown' },
};

function CitationValidationResult({ s, tr }: CitationValidationResultProps) {
  const citing = (tr.citing_cases || []) as CitingCase[];
  const grouped = ['negative', 'caution', 'positive'].map((t) => ({
    treatment: t,
    cases: citing.filter((c) => c.treatment === t),
  })).filter((g) => g.cases.length > 0);
  const badge = BADGE[tr.warning_level || 'unknown'] || BADGE.unknown;
  const read = tr.citing_cases_analyzed;

  return (
    <div className={s.resultCard}>
      <div className={s.toolOverline}>Citation check · CourtListener</div>
      <div className={s.validationBadgeWrapper}>
        <div className={s.validationCaseName}>
          {tr.case_name || 'Unknown Case'}
        </div>
        <div className={s.validationCitation}>{tr.citation}</div>
        {tr.absolute_url && (
          <a className={s.validationCaseLink} href={tr.absolute_url} target="_blank" rel="noopener noreferrer">
            <Icon name="ExternalLink" size={12} /> Open case on CourtListener
          </a>
        )}
      </div>
      <div className={`${s.validationBadge} ${s[badge.className]}`}>
        <Icon name={badge.icon} size={16} />
        {badge.label}
      </div>
      <div className={s.validationMethod}>
        Scan of the language courts use near this citation
        {typeof read === 'number' && read > 0 ? ` in ${read} recent and most-cited citing opinions` : ''}.
        Not an editorial citator — it does not replace Shepard&rsquo;s or KeyCite.
      </div>
      <div className={s.validationGrid}>
        <div className={s.validationItem}>
          <span className={s.validationLabel}>Total Citations</span>
          <span className={s.validationValue}>{(tr.total_citing_cases || 0).toLocaleString()}</span>
        </div>
        <div className={s.validationItem}>
          <span className={s.validationLabel}>Positive</span>
          <span className={s.validationValuePositive}>{tr.positive_citations || 0}</span>
        </div>
        <div className={s.validationItem}>
          <span className={s.validationLabel}>Caution</span>
          <span className={s.validationValue}>{tr.caution_citations || 0}</span>
        </div>
        <div className={s.validationItem}>
          <span className={s.validationLabel}>Negative</span>
          <span className={s.validationValueNegative}>{tr.negative_citations || 0}</span>
        </div>
        {tr.last_cited && (
          <div className={s.validationItem}>
            <span className={s.validationLabel}>Last Cited</span>
            <span className={s.validationValue}>{tr.last_cited}</span>
          </div>
        )}
      </div>

      {grouped.map((g) => (
        <div key={g.treatment} className={s.caseDetailSection}>
          <div className={s.caseDetailSectionTitle}>
            {TREATMENT_LABEL[g.treatment]} ({g.cases.length})
          </div>
          {g.cases.map((c, i) => (
            <div key={`${c.id}-${i}`} className={s.resultRow}>
              <div className={s.resultRowContent}>
                <span className={s.resultRowTitle}>{c.case_name}</span>
                <span className={s.resultRowMeta}>
                  {[c.citation, c.court, c.date_filed].filter(Boolean).join(' • ')}
                </span>
                {c.snippet && (
                  <span className={s.resultSnippet}>
                    {c.context_found ? '' : 'Opening lines: '}“{c.snippet}”
                  </span>
                )}
              </div>
              {c.url && (
                <a href={c.url} target="_blank" rel="noopener noreferrer" title="View on CourtListener">
                  <Icon name="ExternalLink" size={14} className={s.resultRowLinkIcon} />
                </a>
              )}
            </div>
          ))}
        </div>
      ))}

      {tr.notes && tr.notes.length > 0 && (
        <div className={s.analysisNotes}>
          <div className={s.analysisNotesTitle}>How this was checked</div>
          {tr.notes.map((note, i) => (
            <div key={i} className={s.analysisNote}>• {note}</div>
          ))}
        </div>
      )}
      <AiNotice />
    </div>
  );
}

export { CitationValidationResult };
