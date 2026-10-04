import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import JudgeStatsSection from './JudgeStatsSection';

const s = new Proxy({} as Record<string, string>, { get: (_, key) => String(key) });

describe('JudgeStatsSection', () => {
  it('renders nothing without stats', () => {
    const { container } = render(<JudgeStatsSection s={s} judgeIntelStats={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when stats carry no usable fields', () => {
    const { container } = render(<JudgeStatsSection s={s} judgeIntelStats={{}} />);
    expect(container.innerHTML).toBe('');
  });

  it('shows overview averages', () => {
    const { container } = render(
      <JudgeStatsSection
        s={s}
        judgeIntelStats={{
          overview: { avg_citations_per_opinion: 4.2, avg_opinion_length: 2150 },
        }}
      />,
    );
    expect(container.textContent).toContain('Statistics');
    expect(container.textContent).toContain('4.2');
    expect(container.textContent).toContain('2,150');
    expect(container.textContent).toContain('Avg Words/Opinion');
  });

  it('shows day-of-week and citation distribution', () => {
    const { container } = render(
      <JudgeStatsSection
        s={s}
        judgeIntelStats={{
          by_day_of_week: [{ day_of_week: 'Monday', opinions: 12 }],
          citation_distribution: [{ citation_range: '0-5', count: 340 }],
        }}
      />,
    );
    expect(container.textContent).toContain('Opinions by Day of Week');
    expect(container.textContent).toContain('Mon');
    expect(container.textContent).toContain('Citation Distribution');
    expect(container.textContent).toContain('0-5');
    expect(container.textContent).toContain('340');
  });
});
