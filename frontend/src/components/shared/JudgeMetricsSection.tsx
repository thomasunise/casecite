import React from 'react';
import { Icon } from './Icon';
import type { JudgeMetrics, JudgeMetricValue } from '../../types';

interface JudgeMetricsSectionProps {
  s: Record<string, string>;
  metrics: JudgeMetrics | null;
  loading?: boolean;
}

const num = (v: unknown, digits = 1): string | null =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits).replace(/\.0$/, '') : null;

interface Card { key: string; label: string; value: string; detail?: string; quality?: string }

function buildCards(metrics: Record<string, JudgeMetricValue>): Card[] {
  const cards: Card[] = [];
  const m = (k: string) => metrics[k] || {};

  const bench = m('bench_experience');
  if (num(bench.total_years) !== null) {
    cards.push({
      key: 'bench_experience', label: 'Years on the bench', value: `${num(bench.total_years, 0)}`,
      detail: bench.current_position ? String(bench.current_position) : undefined, quality: String(bench.data_quality || ''),
    });
  }
  const impact = m('citation_impact_score');
  if (num(impact.value) !== null) {
    cards.push({
      key: 'citation_impact_score', label: 'Citation impact', value: `${num(impact.value, 2)}`,
      detail: num(impact.avg_citations_per_opinion) !== null ? `${num(impact.avg_citations_per_opinion)} cites per opinion` : undefined,
      quality: String(impact.data_quality || ''),
    });
  }
  const dissent = m('dissent_rate');
  if (num(dissent.value) !== null) {
    cards.push({
      key: 'dissent_rate', label: 'Dissent rate', value: `${num(dissent.value)}%`,
      detail: dissent.dissent_count != null ? `${dissent.dissent_count} of ${dissent.total_opinions_analyzed ?? '?'} typed opinions` : undefined,
      quality: String(dissent.data_quality || ''),
    });
  }
  const concur = m('concurrence_rate');
  if (num(concur.value) !== null) {
    cards.push({ key: 'concurrence_rate', label: 'Concurrence rate', value: `${num(concur.value)}%`, quality: String(concur.data_quality || '') });
  }
  const disp = m('case_disposition_time');
  if (num(disp.value_months) !== null) {
    cards.push({
      key: 'case_disposition_time', label: 'Time to disposition', value: `${num(disp.value_months)} mo`,
      detail: [disp.median_days != null ? `median ${disp.median_days} days` : null, disp.cases_analyzed != null ? `${disp.cases_analyzed} cases` : null].filter(Boolean).join(' · ') || undefined,
      quality: String(disp.data_quality || ''),
    });
  }
  const writing = m('writing_complexity');
  if (num(writing.score) !== null || num(writing.avg_opinion_length_words) !== null) {
    cards.push({
      key: 'writing_complexity', label: 'Writing',
      value: num(writing.avg_opinion_length_words, 0) !== null ? `${Number(writing.avg_opinion_length_words).toLocaleString()} words` : `${num(writing.score)}`,
      detail: [num(writing.avg_sentence_length_words) !== null ? `${num(writing.avg_sentence_length_words)} words/sentence` : null, num(writing.vocabulary_diversity, 2) !== null ? `vocabulary ${num(writing.vocabulary_diversity, 2)}` : null].filter(Boolean).join(' · ') || undefined,
      quality: String(writing.data_quality || ''),
    });
  }
  const lengthTrend = m('opinion_length_trend');
  if (lengthTrend.trend_direction) {
    cards.push({ key: 'opinion_length_trend', label: 'Opinion length trend', value: String(lengthTrend.trend_direction), quality: String(lengthTrend.data_quality || '') });
  }
  const complete = m('data_completeness');
  if (num(complete.score) !== null) {
    cards.push({ key: 'data_completeness', label: 'Data completeness', value: `${num(complete.score, 0)}%`, detail: complete.recommendation ? String(complete.recommendation) : undefined });
  }
  return cards;
}

function JudgeMetricsSection({ s, metrics, loading }: JudgeMetricsSectionProps) {
  if (loading && !metrics) {
    return (
      <div className={s.judgeProfileSection}>
        <h3 className={s.judgeProfileSectionTitle}>Analytics</h3>
        <div className={s.caseLoading}><Icon name="Loader2" size={20} className={s.spinnerIcon} /> Computing analytics...</div>
      </div>
    );
  }
  if (!metrics || metrics.error) return null;
  const values = metrics.metrics || {};
  const cards = buildCards(values);
  const expertise = values.case_type_expertise || {};
  const distribution = (expertise.distribution && typeof expertise.distribution === 'object'
    ? Object.entries(expertise.distribution as Record<string, number>)
    : []).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const methodology = metrics.methodology || {};
  const summary = metrics.summary || {};
  if (cards.length === 0 && distribution.length === 0) return null;

  const tip = (key: string) => {
    const m = methodology[key];
    if (!m) return undefined;
    return [m.description, m.calculation ? `How: ${m.calculation}` : null, m.limitations ? `Limits: ${m.limitations}` : null].filter(Boolean).join('\n\n');
  };

  return (
    <div className={s.judgeProfileSection}>
      <h3 className={s.judgeProfileSectionTitle}>Analytics</h3>
      <div className={s.metricNote}>
        Computed from this judge's cached opinions and dockets. Every figure carries a data-quality note; hover a card for how it is calculated.
      </div>

      {cards.length > 0 && (
        <div className={s.statChipRow}>
          {cards.map((c) => (
            <div key={c.key} className={s.statChip} title={tip(c.key)}>
              <span className={`${s.statChipValue} mono`}>{c.value}</span>
              <span className={s.statChipLabel}>{c.label}</span>
              {c.detail && <span className={s.statChipDetail}>{c.detail}</span>}
              {c.quality && <span className={s.dataQuality}>data: {c.quality}</span>}
            </div>
          ))}
        </div>
      )}

      {distribution.length > 0 && (
        <div className={s.statSubBlock}>
          <div className={s.statSubTitle} title={tip('case_type_expertise')}>
            Case types{expertise.primary_expertise ? ` · most experience: ${String(expertise.primary_expertise)}` : ''}
            {expertise.data_quality ? ` · data: ${String(expertise.data_quality)}` : ''}
          </div>
          <div className={s.mixBars}>
            {(() => {
              const max = Math.max(...distribution.map(([, v]) => Number(v) || 0), 1);
              return distribution.map(([label, v], i) => (
                <div key={i} className={s.mixBarRow}>
                  <span className={s.mixBarLabel} title={label}>{label}</span>
                  <div className={s.mixBarTrack}>
                    <div className={s.mixBarFill} style={{ '--bar-width': `${(Number(v) / max) * 100}%` } as React.CSSProperties} />
                  </div>
                  <span className={`${s.mixBarCount} mono`}>{Number(v).toLocaleString()}</span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}

      {((summary.strengths?.length ?? 0) > 0 || (summary.cautions?.length ?? 0) > 0) && (
        <div className={s.statSubBlock}>
          <div className={s.statSubTitle}>Reading the numbers{summary.data_quality_overall ? ` · overall data: ${summary.data_quality_overall}` : ''}</div>
          {(summary.strengths || []).map((t, i) => <div key={`s${i}`} className={s.judgeProfileItemMeta}>• {t}</div>)}
          {(summary.cautions || []).map((t, i) => <div key={`c${i}`} className={s.judgeProfileItemMeta}>• {t}</div>)}
        </div>
      )}
      {metrics.computed_at && (
        <div className={s.dataQuality}>Computed {String(metrics.computed_at).slice(0, 10)}</div>
      )}
    </div>
  );
}

export { JudgeMetricsSection };
