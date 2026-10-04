import React from 'react';
import type { JudgeStats } from '../../types';

interface JudgeStatsSectionProps {
  s: Record<string, string>;
  judgeIntelStats: JudgeStats | null;
}

function JudgeStatsSection({
  s,
  judgeIntelStats,
}: JudgeStatsSectionProps) {
  if (!judgeIntelStats) return null;

  const overview = judgeIntelStats.overview;
  const days = judgeIntelStats.by_day_of_week ?? [];
  const distribution = judgeIntelStats.citation_distribution ?? [];
  if (!overview && days.length === 0 && distribution.length === 0) return null;

  return (
    <div className={s.judgeProfileSection}>
      <h3 className={s.judgeProfileSectionTitle}>Statistics</h3>

      {overview && (
        <div className={s.statChipRow}>
          {[
            { label: 'Avg Citations/Opinion', value: overview.avg_citations_per_opinion?.toFixed(1) ?? '—' },
            { label: 'Avg Words/Opinion', value: Math.round(overview.avg_opinion_length || 0).toLocaleString() },
          ].map((m, i) => (
            <div key={i} className={s.statChip}>
              <span className={`${s.statChipValue} mono`}>{m.value}</span>
              <span className={s.statChipLabel}>{m.label}</span>
            </div>
          ))}
        </div>
      )}

      {days.length > 0 && (
        <div className={s.statSubBlock}>
          <div className={s.statSubTitle}>Opinions by Day of Week</div>
          <div className={s.statsDayGrid}>
            {days.map((d, i: number) => (
              <div key={i} className={s.statsDayItem}>
                <span className={s.statsDayName}>{d.day_of_week?.slice(0, 3)}</span>
                <span className={`${s.statsDayCount} mono`}>{d.opinions}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {distribution.length > 0 && (
        <div className={s.statSubBlock}>
          <div className={s.statSubTitle}>Citation Distribution</div>
          <div className={s.mixBars}>
            {(() => {
              const maxCount = Math.max(...distribution.map((c) => c.count));
              return distribution.map((c, i: number) => (
                <div key={i} className={s.mixBarRow}>
                  <span className={s.mixBarLabel}>{c.citation_range}</span>
                  <div className={s.mixBarTrack}>
                    <div className={s.mixBarFill} style={{ '--bar-width': `${maxCount > 0 ? (c.count / maxCount) * 100 : 0}%` } as React.CSSProperties} />
                  </div>
                  <span className={`${s.mixBarCount} mono`}>{c.count.toLocaleString()}</span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

export { JudgeStatsSection };
export default JudgeStatsSection;
