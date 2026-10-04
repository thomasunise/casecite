import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import JudgeSearchPanel from './JudgeSearchPanel';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    judgeIntelSearch: '',
    setJudgeIntelSearch: vi.fn(),
    searchJudgesIntel: vi.fn(),
    judgeIntelLoading: false,
    judgeIntelResults: null,
    buildJudgeIntel: vi.fn(),
    ...overrides,
  };
}

describe('JudgeSearchPanel', () => {
  it('renders without crashing', () => {
    const { container } = render(<JudgeSearchPanel {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the judge intelligence header', () => {
    const { container } = render(<JudgeSearchPanel {...defaultProps()} />);
    expect(container.textContent).toContain('Judge Intelligence');
  });

  it('shows the subtitle', () => {
    const { container } = render(<JudgeSearchPanel {...defaultProps()} />);
    expect(container.textContent).toContain('Search any judge for their full profile and analytics.');
  });

  it('has a search input', () => {
    const { container } = render(<JudgeSearchPanel {...defaultProps()} />);
    const input = container.querySelector('input[type="text"]');
    expect(input).toBeTruthy();
  });

  it('has a search button', () => {
    const { container } = render(<JudgeSearchPanel {...defaultProps()} />);
    expect(container.textContent).toContain('Search');
  });

  it('shows error when present in results', () => {
    const results = { error: 'Search failed', judges: null, count: 0 };
    const { container } = render(
      <JudgeSearchPanel {...defaultProps({ judgeIntelResults: results })} />,
    );
    expect(container.textContent).toContain('Search failed');
  });

  it('shows judge results when available', () => {
    const results = {
      judges: [
        { id: 'j-1', name: 'Sonia Sotomayor', name_full: 'Sonia Sotomayor', court: 'Supreme Court', position: 'Associate Justice', appointed_by: 'Obama' },
      ],
      count: 1,
      total_available: 1,
    };
    const { container } = render(
      <JudgeSearchPanel {...defaultProps({ judgeIntelResults: results })} />,
    );
    expect(container.textContent).toContain('Sonia Sotomayor');
    expect(container.textContent).toContain('Supreme Court');
    expect(container.textContent).toContain('Showing 1 judges');
  });
});
