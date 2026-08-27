import { Icon } from './Icon';
import s from './AiNotice.module.css';

export const AI_NOTICE_TEXT =
  'AI-generated. Verify every statement, citation and clause against the source documents and current law before relying on it.';

interface AiNoticeProps {
  className?: string;
}

/**
 * The one "AI-generated — verify before relying" notice, rendered once at
 * the bottom of every generated artifact. Persistent (not dismissible) and
 * deliberately quiet: muted small type under a hairline rule.
 */
export function AiNotice({ className = '' }: AiNoticeProps) {
  return (
    <div role="note" className={`${s.notice} ${className}`.trim()}>
      <Icon name="Sparkles" size={11} className={s.icon} />
      <span>{AI_NOTICE_TEXT}</span>
    </div>
  );
}
