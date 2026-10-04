import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import JudgeProfileTab from './JudgeProfileTab';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    judgeIntelProfile: {
      id: 'judge-1',
      name: 'John Roberts',
      education: [],
      positions: [],
      most_cited_opinions: [],
      opinions_by_court: [],
      opinions_by_year: [],
    },
    loadOpinionFullText: vi.fn(),
    ...overrides,
  };
}

describe('JudgeProfileTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<JudgeProfileTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('renders empty when no profile data', () => {
    const { container } = render(<JudgeProfileTab {...defaultProps()} />);
    // Should render the container but no sections since arrays are empty
    expect(container.innerHTML).not.toBe('');
  });

  it('shows education section when data available', () => {
    const profile = {
      ...defaultProps().judgeIntelProfile,
      education: [
        { school_name: 'Harvard Law School', degree: 'J.D.', degree_year: '1979' },
      ],
    };
    const { container } = render(
      <JudgeProfileTab {...defaultProps({ judgeIntelProfile: profile })} />,
    );
    expect(container.textContent).toContain('Education');
    expect(container.textContent).toContain('Harvard Law School');
    expect(container.textContent).toContain('J.D.');
  });

  it('shows positions section when data available', () => {
    const profile = {
      ...defaultProps().judgeIntelProfile,
      positions: [
        { position_type: 'Chief Justice', court_name: 'Supreme Court', appointer: 'Bush', date_start: '2005', date_termination: null },
      ],
    };
    const { container } = render(
      <JudgeProfileTab {...defaultProps({ judgeIntelProfile: profile })} />,
    );
    expect(container.textContent).toContain('Career');
    expect(container.textContent).toContain('Chief Justice');
    expect(container.textContent).toContain('Supreme Court');
  });

  it('does not render a most-cited section — opinions live in the Opinions section', () => {
    const profile = {
      ...defaultProps().judgeIntelProfile,
      most_cited_opinions: [
        { id: 'op-1', case_name: 'Roe v. Wade', citation: '410 U.S. 113', citation_count: 5000, date_filed: '1973' },
      ],
    };
    const { container } = render(
      <JudgeProfileTab {...defaultProps({ judgeIntelProfile: profile })} />,
    );
    expect(container.textContent).not.toContain('Most Cited Opinions');
  });

  it('shows opinions by court when data available', () => {
    const profile = {
      ...defaultProps().judgeIntelProfile,
      opinions_by_court: [
        { court: 'Supreme Court', count: 150 },
        { court: 'D.C. Circuit', count: 45 },
      ],
    };
    const { container } = render(
      <JudgeProfileTab {...defaultProps({ judgeIntelProfile: profile })} />,
    );
    expect(container.textContent).toContain('Opinions by Court');
    expect(container.textContent).toContain('Supreme Court');
  });
});
