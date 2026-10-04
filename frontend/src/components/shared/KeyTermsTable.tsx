import type { ContractKeyTerm } from '../../api/types';
import s from './KeyTermsTable.module.css';

interface KeyTermsTableProps {
  keyTerms: Record<string, ContractKeyTerm>;
}

// Canonical display order — extra fields returned by the backend are appended.
const FIELD_ORDER = [
  'effective_date',
  'term',
  'renewal',
  'termination',
  'payment_terms',
  'governing_law',
  'liability_cap',
  'indemnification',
  'ip_ownership',
  'confidentiality',
  'assignment',
  'dispute_resolution',
] as const;

const FIELD_LABELS: Record<string, string> = {
  effective_date: 'Effective Date',
  term: 'Term',
  renewal: 'Renewal',
  termination: 'Termination',
  payment_terms: 'Payment Terms',
  governing_law: 'Governing Law',
  liability_cap: 'Liability Cap',
  indemnification: 'Indemnification',
  ip_ownership: 'IP Ownership',
  confidentiality: 'Confidentiality',
  assignment: 'Assignment',
  dispute_resolution: 'Dispute Resolution',
};

function labelFor(field: string): string {
  return FIELD_LABELS[field]
    || field.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export function KeyTermsTable({ keyTerms }: KeyTermsTableProps) {
  const known = FIELD_ORDER.filter((f) => keyTerms[f]);
  const extras = Object.keys(keyTerms).filter((f) => !(FIELD_ORDER as readonly string[]).includes(f));
  const fields = [...known, ...extras];

  if (fields.length === 0) {
    return <p className={s.emptyNote}>No key terms were extracted from this contract.</p>;
  }

  return (
    <div className={s.table}>
      {fields.map((field) => {
        const term = keyTerms[field];
        return (
          <div key={field} className={s.row}>
            <div className={s.fieldLabel}>{labelFor(field)}</div>
            <div className={s.fieldContent}>
              <div className={s.value}>
                {term.value}
                {!term.verified && <span className={s.unverifiedTag}>(unverified)</span>}
              </div>
              {term.verified && term.quote && (
                <blockquote className={s.quote}>{term.quote}</blockquote>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
