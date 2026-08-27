import { useEffect, useMemo, useRef, useState } from 'react';
import type { ContractComparison } from '../../api/types';
import { Icon } from './Icon';
import s from './ComparisonSplitView.module.css';

export interface SplitDoc {
  id: string;
  label: string;
  text: string;
}

interface ComparisonSplitViewProps {
  /** 2-4 documents, first is the comparison baseline. */
  docs: SplitDoc[];
  /** Pairwise comparisons (baseline vs each other doc). Empty = plain panes. */
  comparisons: ContractComparison[];
  loading: boolean;
  /** Bumped by the store when a clause is selected from chat or Sources. */
  jump: { comparisonIndex: number; clauseIndex: number; seq: number } | null;
  onClose: () => void;
}

interface Segment {
  text: string;
  /** `${comparisonIndex}-${clauseIndex}` when highlighted. */
  clauseKey: string | null;
  status?: string;
}

/** Split one document's text into plain/highlighted segments from every
    comparison that touches it. Overlapping spans keep the first. */
function buildSegments(doc: SplitDoc, comparisons: ContractComparison[]): Segment[] {
  const spans: Array<{ start: number; end: number; status: string; clauseKey: string }> = [];
  comparisons.forEach((comparison, ci) => {
    const side = comparison.document_id_a === doc.id ? 'a'
      : comparison.document_id_b === doc.id ? 'b' : null;
    if (!side) return;
    comparison.clauses.forEach((c, i) => {
      const start = side === 'a' ? c.span_a_start : c.span_b_start;
      const end = side === 'a' ? c.span_a_end : c.span_b_end;
      if (start != null && end != null && end > start && end <= doc.text.length) {
        spans.push({ start, end, status: c.status, clauseKey: `${ci}-${i}` });
      }
    });
  });
  spans.sort((x, y) => x.start - y.start);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const sp of spans) {
    if (sp.start < cursor) continue; // overlap — first span wins
    if (sp.start > cursor) segments.push({ text: doc.text.slice(cursor, sp.start), clauseKey: null });
    segments.push({ text: doc.text.slice(sp.start, sp.end), clauseKey: sp.clauseKey, status: sp.status });
    cursor = sp.end;
  }
  if (cursor < doc.text.length) segments.push({ text: doc.text.slice(cursor), clauseKey: null });
  return segments;
}

const STATUS_CLASS: Record<string, string> = {
  changed: 'markChanged',
  added: 'markAdded',
  removed: 'markRemoved',
  unchanged: 'markUnchanged',
};

/**
 * 2-4 contracts side by side. With comparison results, every verified quote is
 * highlighted in place — click a clause chip (or a Sources row) and the panes
 * scroll to that clause's language in each document that carries it.
 */
export function ComparisonSplitView({ docs, comparisons, loading, jump, onClose }: ComparisonSplitViewProps) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const paneRefs = useRef<Array<HTMLDivElement | null>>([]);

  const segmentsByDoc = useMemo(
    () => docs.map((d) => buildSegments(d, comparisons)),
    [docs, comparisons],
  );

  const scrollToClause = (key: string) => {
    setActiveKey(key);
    for (const pane of paneRefs.current) {
      const mark = pane?.querySelector(`[data-clause="${key}"]`);
      mark?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  // External jumps (chat card / Sources panel rows).
  useEffect(() => {
    if (jump) scrollToClause(`${jump.comparisonIndex}-${jump.clauseIndex}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jump?.seq]);

  const activeClause = (() => {
    if (!activeKey) return null;
    const [ci, i] = activeKey.split('-').map(Number);
    return comparisons[ci]?.clauses[i] ?? null;
  })();

  return (
    <div className={s.wrapper}>
      <div className={s.header}>
        <div className={s.headerInfo}>
          <p className={s.overline}>
            {comparisons.length > 0 ? 'Side-by-side comparison' : 'Side-by-side documents'}
          </p>
          <div className={s.labels}>
            {docs.map((d, i) => (
              <span key={d.id} className={s.labelGroup}>
                {i > 0 && <Icon name="ArrowRight" size={13} className={s.labelArrow} />}
                <span className={s.labelChip}>{d.label}</span>
              </span>
            ))}
          </div>
        </div>
        <button className={s.closeBtn} onClick={onClose} aria-label="Close split view">
          <Icon name="X" size={15} />
        </button>
      </div>

      {/* Clause strip: every finding across every pair; click to spotlight */}
      {comparisons.length > 0 && (
        <div className={s.clauseStrip}>
          {comparisons.map((comparison, ci) =>
            comparison.clauses.map((c, i) => (
              <button
                key={`${ci}-${i}`}
                className={`${s.clauseChip} ${activeKey === `${ci}-${i}` ? s.clauseChipActive : ''}`}
                onClick={() => scrollToClause(`${ci}-${i}`)}
                title={c.summary}
              >
                <span className={`${s.statusDot} ${s[STATUS_CLASS[c.status]]}`} />
                {comparisons.length > 1 ? `${comparison.label_b}: ${c.topic}` : c.topic}
              </button>
            )),
          )}
        </div>
      )}
      {comparisons.length === 0 && !loading && (
        <div className={s.compareHintStrip}>
          <Icon name="GitCompare" size={13} />
          <span>
            Say <strong>"compare these files"</strong> in the composer below — add what
            to focus on if you like. Differences highlight right here.
          </span>
        </div>
      )}

      {loading ? (
        <div className={s.loading}>
          <Icon name="Loader2" size={20} className={s.spin} />
          <span>Loading documents…</span>
        </div>
      ) : (
        <div className={`${s.panes} ${docs.length >= 4 ? s.panesGrid2x2 : ''}`}>
          {docs.map((doc, di) => (
            <div key={doc.id} className={s.pane}>
              <div className={s.paneHeader}>{doc.label}</div>
              <div className={s.paneScroll} ref={(el) => { paneRefs.current[di] = el; }}>
                {!doc.text ? (
                  <p className={s.paneEmpty}>Document text unavailable.</p>
                ) : (
                  <div className={s.paneText}>
                    {segmentsByDoc[di].map((seg, i) =>
                      seg.clauseKey == null ? (
                        <span key={i}>{seg.text}</span>
                      ) : (
                        <mark
                          key={i}
                          data-clause={seg.clauseKey}
                          className={`${s.mark} ${s[STATUS_CLASS[seg.status || 'changed']]} ${
                            activeKey === seg.clauseKey ? s.markActive : ''
                          }`}
                          onClick={() => scrollToClause(seg.clauseKey!)}
                        >
                          {seg.text}
                        </mark>
                      ),
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeClause && (
        <div className={s.activeSummary}>
          <span className={`${s.statusChipInline} ${s[STATUS_CLASS[activeClause.status]]}`}>
            {activeClause.status}
          </span>
          <strong>{activeClause.topic}:</strong>
          <span>{activeClause.summary}</span>
        </div>
      )}
    </div>
  );
}
