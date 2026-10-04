import type { ContractAnalysisResult } from '../../api/types';
import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import { KeyTermsTable } from './KeyTermsTable';
import { ContractIssueCard } from './ContractIssueCard';
import { ObligationsList } from './ObligationsList';
import { contractTypeLabel } from '../../utils';
import s from './ContractAnalysisMessage.module.css';

interface ContractAnalysisMessageProps {
  analysis: ContractAnalysisResult;
  exporting: boolean;
  onExport: (analysisId: string, format: 'docx' | 'md') => void;
}

// Importance ordering only — never shown as labels or scores in the UI.
const SEVERITY_ORDER = ['critical', 'major', 'minor', 'informational'] as const;

/**
 * A full contract analysis rendered as rich content inside an assistant chat
 * message: header + export buttons, executive summary, key terms, issues
 * (most important first), and obligations & deadlines.
 */
export function ContractAnalysisMessage({ analysis, exporting, onExport }: ContractAnalysisMessageProps) {
  const issues = analysis.issues ?? [];
  const rank = (sev: string) => {
    const i = (SEVERITY_ORDER as readonly string[]).indexOf(sev);
    return i === -1 ? SEVERITY_ORDER.length : i;
  };
  const orderedIssues = [...issues].sort((a, b) => rank(a.severity) - rank(b.severity));

  return (
    <div className={s.wrapper}>
      {/* Header */}
      <div className={s.header}>
        <div className={s.headText}>
          <p className={s.overline}>Contract Analysis</p>
          <h2 className={s.title}>
            {contractTypeLabel(analysis.contract_type)}
            {analysis.representing && <span className={s.titleMeta}> · representing {analysis.representing}</span>}
          </h2>
          <div className={s.meta}>
            {analysis.posture && <span>Posture: {analysis.posture}</span>}
            {analysis.parties.length > 0 && (
              <span>{analysis.parties.map((p) => p.canonical_name).join(' · ')}</span>
            )}
          </div>
        </div>
        <div className={s.headerActions}>
          <button className={s.exportBtn} onClick={() => onExport(analysis.analysis_id, 'docx')} disabled={exporting}>
            <Icon name="Download" size={13} /> Word
          </button>
          <button className={s.exportBtn} onClick={() => onExport(analysis.analysis_id, 'md')} disabled={exporting}>
            <Icon name="Download" size={13} /> Markdown
          </button>
        </div>
      </div>

      {/* Executive summary */}
      {analysis.executive_summary && (
        <div className={s.section}>
          <h3 className={s.sectionTitle}>Executive Summary</h3>
          <p className={s.summaryText}>{analysis.executive_summary}</p>
        </div>
      )}

      {/* Key terms */}
      <div className={s.section}>
        <h3 className={s.sectionTitle}>Key Terms</h3>
        <KeyTermsTable keyTerms={analysis.key_terms} />
      </div>

      {/* Issues — most important first, no scoring labels */}
      <div className={s.section}>
        <h3 className={s.sectionTitle}>Issues</h3>
        {issues.length === 0 && <p className={s.emptyNote}>No issues were flagged.</p>}
        <div className={s.issueGroupList}>
          {orderedIssues.map((issue) => <ContractIssueCard key={issue.ref} issue={issue} />)}
        </div>
      </div>

      {/* Obligations & deadlines */}
      <div className={s.section}>
        <h3 className={s.sectionTitle}>Obligations &amp; Deadlines</h3>
        <ObligationsList obligations={analysis.obligations} deadlines={analysis.deadlines} />
      </div>

      <AiNotice />
    </div>
  );
}
