import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SourcesList } from './SourcesList';

vi.mock('./Icon', () => ({
  Icon: ({ name, ...rest }: any) => <span data-testid={`icon-${name}`} {...rest} />,
}));

const s = new Proxy({} as Record<string, string>, { get: (_, key) => String(key) });

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s,
    allCitations: [] as any[],
    setSelectedCitation: vi.fn(),
    ...overrides,
  };
}

describe('SourcesList', () => {
  it('renders without crashing', () => {
    const { container } = render(<SourcesList {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows Sources (0) when empty', () => {
    render(<SourcesList {...defaultProps()} />);
    expect(screen.getByText('Sources (0)')).toBeTruthy();
  });

  it('shows empty state message when no citations', () => {
    render(<SourcesList {...defaultProps()} />);
    expect(screen.getByText('No sources yet')).toBeTruthy();
    expect(screen.getByText('Run a search to see cited sources')).toBeTruthy();
  });

  it('marks a below-threshold source as a weak match, without a score', () => {
    const citations = [
      { id: '1', source: 'Lease.pdf', type: 'document', confidence: 18, similarity: 0.18, weakMatch: true },
    ];
    const { container } = render(<SourcesList {...defaultProps({ allCitations: citations })} />);
    expect(screen.getByText('Weak match')).toBeTruthy();
    expect(container.textContent).not.toContain('%');
    expect(container.textContent).not.toContain('0.18');
  });

  it('renders citations when provided', () => {
    const citations = [
      { id: '1', source: 'Miranda v. Arizona', type: 'case_law', confidence: 95, was_cited_by_ai: true },
      { id: '2', source: 'Contract.pdf', type: 'document', confidence: 80, was_cited_by_ai: false },
    ];
    render(<SourcesList {...defaultProps({ allCitations: citations })} />);
    expect(screen.getByText('Sources (2)')).toBeTruthy();
    expect(screen.getByText('Miranda v. Arizona')).toBeTruthy();
    expect(screen.getByText('Contract.pdf')).toBeTruthy();
  });

  it('never shows scores, percentages, or match-strength tiers', () => {
    const citations = [
      { id: '1', source: 'Test Case', type: 'case_law', confidence: 95, was_cited_by_ai: false },
    ];
    const { container } = render(<SourcesList {...defaultProps({ allCitations: citations })} />);
    expect(container.textContent).not.toContain('%');
    expect(container.textContent).not.toContain('Strong match');
    expect(container.textContent).not.toContain('95');
  });

  it('shows binary verification badges when the citation carries a verdict', () => {
    const citations = [
      { id: '1', source: 'Verified.pdf', type: 'document', confidence: 95, verified: true },
      { id: '2', source: 'Shaky.pdf', type: 'document', confidence: 40, verified: false },
    ];
    const { container } = render(<SourcesList {...defaultProps({ allCitations: citations })} />);
    expect(container.textContent).toContain('Verified');
    expect(container.textContent).toContain('Unverified');
  });

  it('collapses multiple chunks of one document into a single source with passage count', () => {
    const citations = [
      { id: '1', source: 'Lease.pdf', type: 'document', confidence: 44, was_cited_by_ai: true },
      { id: '2', source: 'Lease.pdf', type: 'document', confidence: 31, was_cited_by_ai: false },
      { id: '3', source: 'Lease.pdf', type: 'document', confidence: 27, was_cited_by_ai: false },
    ];
    const { container } = render(<SourcesList {...defaultProps({ allCitations: citations })} />);
    expect(container.textContent).toContain('Sources (1)');
    expect(container.textContent).toContain('3 passages');
  });
});
