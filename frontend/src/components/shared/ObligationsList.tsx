import type { ContractDeadlineItem, ContractObligation } from '../../api/types';
import { Icon } from './Icon';
import s from './ObligationsList.module.css';

interface ObligationsListProps {
  obligations: ContractObligation[];
  deadlines: ContractDeadlineItem[];
}

function deadlineLabel(d: ContractDeadlineItem): string {
  if (d.resolved_date) {
    const date = new Date(d.resolved_date);
    if (!Number.isNaN(date.getTime())) {
      return `${d.description} — ${date.toLocaleDateString()}`;
    }
  }
  return d.description;
}

export function ObligationsList({ obligations, deadlines }: ObligationsListProps) {
  if (obligations.length === 0 && deadlines.length === 0) {
    return <p className={s.emptyNote}>No obligations or deadlines were extracted.</p>;
  }

  return (
    <div className={s.wrapper}>
      {obligations.map((o, i) => (
        <div key={`ob-${i}`} className={s.row}>
          <div className={s.mainLine}>
            <span className={s.subject}>{o.subject_party || 'Unassigned party'}</span>
            <span className={s.dash}>—</span>
            <span className={s.action}>{o.modal} {o.action}</span>
            {o.object_text && (
              <>
                <span className={s.dash}>—</span>
                <span className={s.objectText}>{o.object_text}</span>
              </>
            )}
          </div>
          <div className={s.metaLine}>
            {o.category && <span className={s.categoryChip}>{o.category}</span>}
            {(o.deadlines || []).map((d, j) => (
              <span key={`obd-${i}-${j}`} className={s.deadlineChip}>
                <Icon name="Clock" size={11} /> {d}
              </span>
            ))}
          </div>
        </div>
      ))}

      {deadlines.length > 0 && (
        <div className={s.deadlineBlock}>
          <div className={s.deadlineHeader}>Deadlines</div>
          <div className={s.deadlineChips}>
            {deadlines.map((d, i) => (
              <span key={`dl-${i}`} className={s.deadlineChip} title={d.matched_text || undefined}>
                <Icon name="CalendarClock" size={11} /> {deadlineLabel(d)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
