import type { ContractIssue } from '../../api/types';
import { Icon } from './Icon';
import s from './ContractIssueCard.module.css';

interface ContractIssueCardProps {
  issue: ContractIssue;
}

export function ContractIssueCard({ issue }: ContractIssueCardProps) {
  return (
    <div className={s.card}>
      <div className={s.headerRow}>
        <span className={s.title}>{issue.title}</span>
        {issue.grounding === 'unverified' && (
          <span className={s.unverifiedTag}>(unverified)</span>
        )}
      </div>
      <p className={s.why}>{issue.why}</p>
      {issue.grounding === 'span' && issue.matched_text && (
        <blockquote className={s.quote}>{issue.matched_text}</blockquote>
      )}
      {issue.grounding === 'absence' && (
        <div className={s.absenceNote}>
          <Icon name="SearchX" size={13} /> Clause not found in document
        </div>
      )}
      {issue.suggested_language && (
        <div className={s.suggestion}>
          <div className={s.suggestionLabel}>Suggested language</div>
          <div className={s.suggestionText}>{issue.suggested_language}</div>
        </div>
      )}
    </div>
  );
}
