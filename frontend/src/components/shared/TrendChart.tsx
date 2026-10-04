import { Icon } from './Icon';
import type { TrendYear } from './ToolResultsArea';

interface TrendChartProps {
  s: Record<string, string>;
  topic: string;
  years: TrendYear[];
  totalCases?: number;
  trend?: string;
  trendBasis?: { from_year: number; to_year: number };
  currentYearPartial?: boolean;
  yearsFailed?: number;
}

const TREND_LABEL: Record<string, { icon: string; label: string }> = {
  increasing: { icon: 'TrendingUp', label: 'Increasing' },
  decreasing: { icon: 'TrendingDown', label: 'Decreasing' },
  stable: { icon: 'Minus', label: 'Stable' },
  insufficient: { icon: 'Minus', label: 'Too few years' },
};

function TrendChart({ s, topic, years, totalCases, trend, trendBasis, currentYearPartial, yearsFailed }: TrendChartProps) {
  // A sweep that mostly failed is a rate-limit event, not a trend — say so
  // plainly instead of charting one or two surviving bars as if they were
  // the whole story.
  if (years.length < 3 && (yearsFailed ?? 0) > years.length) {
    return (
      <div className={s.trendCard}>
        <div className={s.trendOverline}>Case-law Trend · CourtListener</div>
        <div className={s.trendTitle}>"{topic}"</div>
        <div className={s.trendNote}>
          <Icon name="AlertCircle" size={12} /> CourtListener is rate-limiting yearly counts right now
          ({yearsFailed} of {years.length + (yearsFailed ?? 0)} years unavailable). Wait a minute and run the search again.
        </div>
      </div>
    );
  }
  if (years.length === 0) return null;

  const maxCount = Math.max(...years.map((yr) => yr.count), 1);
  const lastYear = years[years.length - 1].year;
  const completeYears = currentYearPartial ? years.filter((y) => y.year !== lastYear) : years;
  const peak = (completeYears.length ? completeYears : years).reduce((a, b) => (b.count > a.count ? b : a), years[0]);
  const total = totalCases ?? years.reduce((sum: number, y) => sum + y.count, 0);
  // Keep ~9 x-labels regardless of span; the last year is always labeled.
  const labelStep = Math.max(1, Math.ceil(years.length / 9));
  const trendInfo = TREND_LABEL[trend || ''] || TREND_LABEL.stable;

  return (
    <div className={s.trendCard}>
      <div className={s.trendOverline}>Case-law Trend · CourtListener</div>
      <div className={s.trendTitle}>"{topic}"</div>

      <div className={s.trendStatsRow}>
        <div className={s.trendStat}>
          <span className={`${s.trendStatValue} mono`}>{total.toLocaleString()}</span>
          <span className={s.trendStatLabel}>Cases {years[0].year}–{lastYear}</span>
        </div>
        <div className={s.trendStat}>
          <span className={`${s.trendStatValue} mono`}>{peak.year}</span>
          <span className={s.trendStatLabel}>Peak · {peak.count.toLocaleString()} cases</span>
        </div>
        <div className={s.trendStat}>
          <span className={s.trendStatValue}>
            <Icon name={trendInfo.icon} size={16} />
          </span>
          <span className={s.trendStatLabel}>
            {trendInfo.label}
            {trendBasis && trend !== 'insufficient' ? ` · ${trendBasis.from_year}→${trendBasis.to_year}` : ''}
          </span>
        </div>
      </div>

      <div className={s.trendBars}>
        {years.map((y, i) => {
          const partial = currentYearPartial && y.year === lastYear;
          return (
            <div key={i} className={s.trendBarCol}>
              <div className={s.trendTip}>{y.year} · {y.count.toLocaleString()} cases{partial ? ' so far' : ''}</div>
              <div
                className={`${s.trendBarFill} ${y.count > 0 ? s.trendBarFillActive : ''} ${partial ? s.trendBarFillPartial : ''}`}
                style={{ height: `${(y.count / maxCount) * 128}px` }}
              />
              <span className={`${s.trendBarYear} mono`}>
                {(i % labelStep === 0 || i === years.length - 1) ? y.year : ''}
              </span>
            </div>
          );
        })}
      </div>

      {currentYearPartial && (
        <div className={s.trendNote}>
          <Icon name="Info" size={11} /> {lastYear} is still in progress; it is shown but not counted toward the trend.
        </div>
      )}
      {(yearsFailed ?? 0) > 0 && (
        <div className={s.trendNote}>
          <Icon name="AlertCircle" size={11} /> {yearsFailed} year{yearsFailed !== 1 ? 's' : ''} could not be counted (rate-limited) and {yearsFailed !== 1 ? 'are' : 'is'} not shown.
        </div>
      )}
    </div>
  );
}

export { TrendChart };
