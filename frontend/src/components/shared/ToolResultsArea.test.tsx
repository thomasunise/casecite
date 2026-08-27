import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ToolResultsArea } from './ToolResultsArea';

vi.mock('./Icon', () => ({
  Icon: ({ name, ...rest }: any) => <span data-testid={`icon-${name}`} {...rest} />,
}));

const s = new Proxy({} as Record<string, string>, { get: (_, key) => String(key) });

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s,
    tr: null as any,
    activeTool: null as any,
    toolInput: '',
    toolLoading: false,
    toolApiSlow: false,
    selectedCase: null,
    selectedJudge: null,
    caseLoading: false,
    selectedDocket: null,
    docketLoading: false,
    loadDocketDetail: vi.fn(),
    setSelectedDocket: vi.fn(),
    loadPrecedentCase: vi.fn(),
    loadCaseDetail: vi.fn(),
    setSelectedCase: vi.fn(),
    setSelectedJudge: vi.fn(),
    handleCompareCase: vi.fn(),
    loadMoreResults: vi.fn(),
    setActiveMode: vi.fn(),
    setActiveTool: vi.fn(),
    setToolResult: vi.fn(),
    buildJudgeIntel: vi.fn(),
    ...overrides,
  };
}

describe('ToolResultsArea', () => {
  it('renders without crashing', () => {
    const { container } = render(<ToolResultsArea {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows error when tr has error', () => {
    render(<ToolResultsArea {...defaultProps({ tr: { error: 'Something went wrong' } })} />);
    expect(screen.getByText('Something went wrong')).toBeTruthy();
  });

  it('shows API slow warning when toolApiSlow and toolLoading', () => {
    render(<ToolResultsArea {...defaultProps({ toolApiSlow: true, toolLoading: true })} />);
    expect(screen.getByText('CourtListener API is Taking a While')).toBeTruthy();
  });

  it('does not show API slow warning when not loading', () => {
    const { container } = render(<ToolResultsArea {...defaultProps({ toolApiSlow: true, toolLoading: false })} />);
    expect(container.textContent).not.toContain('CourtListener API is Taking a While');
  });

  it('renders case search results for case-lookup', () => {
    const tr = {
      results: [
        { id: 'c1', case_name: 'Miranda v. Arizona', court: 'SCOTUS', date_filed: '1966-06-13', times_cited: 5000 },
      ],
      count: 1,
    };
    render(<ToolResultsArea {...defaultProps({ activeTool: { id: 'case-lookup' }, tr })} />);
    expect(screen.getByText('Miranda v. Arizona')).toBeTruthy();
    expect(screen.getByText('1 cases found')).toBeTruthy();
  });

  it('renders citation validation result', () => {
    const tr = {
      case_name: 'Roe v. Wade',
      citation: '410 U.S. 113',
      warning_level: 'warning',
      total_citing_cases: 100,
      positive_citations: 60,
      negative_citations: 40,
    };
    render(<ToolResultsArea {...defaultProps({ activeTool: { id: 'validate-citation' }, tr })} />);
    expect(screen.getByText('Roe v. Wade')).toBeTruthy();
    expect(screen.getByText('410 U.S. 113')).toBeTruthy();
    expect(screen.getByText('Negative language found — read before relying')).toBeTruthy();
    expect(screen.getByText(/Not an editorial citator/)).toBeTruthy();
  });

  it('renders precedents results', () => {
    const tr = {
      precedents: [
        { case_name: 'Brown v. Board', citation: '347 U.S. 483', citation_count: 3000 },
      ],
      count: 1,
    };
    render(<ToolResultsArea {...defaultProps({ activeTool: { id: 'precedents' }, tr })} />);
    expect(screen.getByText('Brown v. Board')).toBeTruthy();
  });

  it('renders docket results', () => {
    const tr = {
      dockets: [
        { case_name: 'Smith v. Jones', court: 'SDNY', docket_number: '1:24-cv-00001' },
      ],
      count: 1,
    };
    render(<ToolResultsArea {...defaultProps({ activeTool: { id: 'dockets' }, tr })} />);
    expect(screen.getByText('Smith v. Jones')).toBeTruthy();
  });

  it('renders trends with bar chart', () => {
    const tr = {
      years: [
        { year: 2023, count: 50 },
        { year: 2024, count: 75 },
      ],
      total_cases: 125,
      trend: 'increasing',
    };
    render(<ToolResultsArea {...defaultProps({ activeTool: { id: 'trends' }, tr, toolInput: 'qualified immunity' })} />);
    expect(screen.getByText('"qualified immunity"')).toBeTruthy();
    expect(screen.getByText('125')).toBeTruthy();
    expect(screen.getByText(/Peak · 75 cases/)).toBeTruthy();
    expect(screen.getByText('2024 · 75 cases')).toBeTruthy();
  });
});
