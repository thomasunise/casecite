import { useContractsStore } from '../../stores/contractsStore';
import s from './ComparisonPanel.module.css';

const STATUS_CLASS: Record<string, string> = {
  changed: 'statusChanged',
  added: 'statusAdded',
  removed: 'statusRemoved',
  unchanged: 'statusUnchanged',
};

/**
 * The latest contract comparison's findings, listed in the Sources panel.
 * Clicking a finding opens the side-by-side view and scrolls both documents
 * to that clause's highlighted language.
 */
export function ComparisonPanel() {
  const messages = useContractsStore((st) => st.messages);
  const jumpToComparisonClause = useContractsStore((st) => st.jumpToComparisonClause);

  // Latest comparison OR comparison set in the conversation.
  const comparisons = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.kind === 'comparison_set' && m.comparisonSet) return m.comparisonSet.comparisons;
      if (m.kind === 'comparison' && m.comparison) return [m.comparison];
    }
    return null;
  })();

  if (!comparisons || comparisons.length === 0) return null;

  return (
    <div className={s.panel}>
      {comparisons.map((comparison, ci) => (
        <div key={ci}>
          <div className={s.labels}>
            {comparison.label_a} → {comparison.label_b}
          </div>
          {comparison.clauses.map((c, i) => (
            <button
              key={i}
              className={s.row}
              onClick={() => jumpToComparisonClause(comparison, i)}
              title="Show in side-by-side view"
            >
              <span className={`${s.statusChip} ${s[STATUS_CLASS[c.status]]}`}>{c.status}</span>
              <span className={s.rowContent}>
                <span className={s.topic}>{c.topic}</span>
                <span className={s.summary}>{c.summary}</span>
              </span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
