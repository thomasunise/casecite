import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import JudgeOpinionsTab from './JudgeOpinionsTab';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    judgeId: 'judge-1',
    selectedOpinion: null,
    setSelectedOpinion: vi.fn(),
    loadOpinionFullText: vi.fn(),
    judgeIntelOpinionQuery: '',
    setJudgeIntelOpinionQuery: vi.fn(),
    judgeIntelOpinionSort: 'citations' as const,
    queryJudgeOpinions: vi.fn(),
    judgeIntelLoading: false,
    judgeIntelOpinions: null,
    ...overrides,
  };
}

describe('JudgeOpinionsTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<JudgeOpinionsTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the opinion search box', () => {
    const { container } = render(<JudgeOpinionsTab {...defaultProps()} />);
    const input = container.querySelector('input[type="text"]');
    expect(input).toBeTruthy();
  });

  it('shows sort pills and requests the chosen order', () => {
    const queryJudgeOpinions = vi.fn();
    const { getByText } = render(
      <JudgeOpinionsTab {...defaultProps({ queryJudgeOpinions })} />,
    );
    getByText('Newest').click();
    expect(queryJudgeOpinions).toHaveBeenCalledWith('judge-1', '', 0, 'date');
    getByText('Most Cited').click();
    expect(queryJudgeOpinions).toHaveBeenCalledWith('judge-1', '', 0, 'citations');
  });

  it('shows loading state', () => {
    const { container } = render(
      <JudgeOpinionsTab {...defaultProps({ judgeIntelLoading: true })} />,
    );
    expect(container.textContent).toContain('Loading opinions...');
  });

  it('shows opinions list when results available', () => {
    const opinions = {
      total: 2,
      opinions: [
        { id: 'op-1', case_name: 'Smith v. Jones', court: 'District Court', date_filed: '2025-06-01', citation_count: 10, snippet: 'This case concerns...' },
        { id: 'op-2', case_name: 'Doe v. Roe', court: 'Circuit Court', date_filed: '2024-03-15', citation_count: 5, snippet: 'The court held...' },
      ],
    };
    const { container } = render(
      <JudgeOpinionsTab {...defaultProps({ judgeIntelOpinions: opinions })} />,
    );
    expect(container.textContent).toContain('Smith v. Jones');
    expect(container.textContent).toContain('Doe v. Roe');
    expect(container.textContent).toContain('2 opinions');
  });

  it('shows selected opinion full view', () => {
    const opinion = {
      id: 'op-1',
      case_name: 'Smith v. Jones',
      court: 'District Court',
      date_filed: '2025-06-01',
      citation: '100 F.Supp.3d 200',
      full_text: 'Full opinion text goes here.',
    };
    const { container } = render(
      <JudgeOpinionsTab {...defaultProps({ selectedOpinion: opinion })} />,
    );
    expect(container.textContent).toContain('Smith v. Jones');
    expect(container.textContent).toContain('Full opinion text goes here.');
    expect(container.textContent).toContain('Back to opinions');
  });

  it('shows load more button when more opinions available', () => {
    const opinions = {
      total: 50,
      opinions: [
        { id: 'op-1', case_name: 'Smith v. Jones', court: 'District Court', date_filed: '2025-06-01' },
      ],
    };
    const { container } = render(
      <JudgeOpinionsTab {...defaultProps({ judgeIntelOpinions: opinions })} />,
    );
    expect(container.textContent).toContain('Load More');
  });
});
