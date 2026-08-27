import { useState } from 'react';
import type { ContractComparison, ContractComparisonClause } from '../../api/types';
import { Icon } from './Icon';
import s from './ComparisonCard.module.css';

interface ComparisonCardProps {
  comparison: ContractComparison;
  /** Open the split-screen view, optionally jumped to one clause. */
  onOpenSplitView?: (clauseIndex?: number) => void;
}

const STATUS_CLASS: Record<ContractComparisonClause['status'], string> = {
  changed: 'statusChanged',
  added: 'statusAdded',
  removed: 'statusRemoved',
  unchanged: 'statusUnchanged',
};

/**
 * A two-contract comparison rendered inside an assistant chat message: the
 * overall summary, then per-clause rows with a status chip and expandable
 * quotes from each side. Quotes that failed verbatim verification carry the
 * house "(unverified)" tag.
 */
export function ComparisonCard({ comparison, onOpenSplitView }: ComparisonCardProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className={s.wrapper}>
      <div className={s.header}>
        <div>
          <p className={s.overline}>Contract Comparison</p>
          <div className={s.labels}>
            <span className={s.labelChip}>{comparison.label_a}</span>
            <Icon name="ArrowRight" size={13} className={s.labelArrow} />
            <span className={s.labelChip}>{comparison.label_b}</span>
          </div>
        </div>
        {onOpenSplitView && (
          <button className={s.splitViewBtn} onClick={() => onOpenSplitView()}>
            <Icon name="Columns2" size={13} /> View side by side
          </button>
        )}
      </div>

      {comparison.overall && <p className={s.overall}>{comparison.overall}</p>}

      <div className={s.clauseList}>
        {comparison.clauses.map((clause, i) => {
          const isOpen = expanded === i;
          const hasQuotes = !!(clause.quote_a || clause.quote_b);
          const hasSpans = clause.span_a_start != null || clause.span_b_start != null;
          return (
            <div key={i} className={s.clause}>
              <div className={s.clauseRowWrap}>
                <button
                  className={s.clauseRow}
                  onClick={() => hasQuotes && setExpanded(isOpen ? null : i)}
                  disabled={!hasQuotes}
                >
                  <span className={`${s.statusChip} ${s[STATUS_CLASS[clause.status]]}`}>
                    {clause.status}
                  </span>
                  <span className={s.topic}>{clause.topic}</span>
                  <span className={s.summary}>{clause.summary}</span>
                  {hasQuotes && (
                    <Icon name={isOpen ? 'ChevronUp' : 'ChevronDown'} size={13} className={s.chevron} />
                  )}
                </button>
                {onOpenSplitView && hasSpans && (
                  <button
                    className={s.locateBtn}
                    title="Show this clause in the side-by-side view"
                    onClick={() => onOpenSplitView(i)}
                  >
                    <Icon name="Crosshair" size={13} />
                  </button>
                )}
              </div>

              {isOpen && (
                <div className={s.quotes}>
                  {clause.quote_a && (
                    <div className={s.quoteBlock}>
                      <div className={s.quoteLabel}>
                        {comparison.label_a}
                        {clause.verified_a === false && (
                          <span className={s.unverifiedTag}>(unverified)</span>
                        )}
                      </div>
                      <blockquote className={s.quote}>{clause.quote_a}</blockquote>
                    </div>
                  )}
                  {clause.quote_b && (
                    <div className={s.quoteBlock}>
                      <div className={s.quoteLabel}>
                        {comparison.label_b}
                        {clause.verified_b === false && (
                          <span className={s.unverifiedTag}>(unverified)</span>
                        )}
                      </div>
                      <blockquote className={s.quote}>{clause.quote_b}</blockquote>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
