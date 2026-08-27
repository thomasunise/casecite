import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CaseComparisonModal } from './CaseComparisonModal';

describe('CaseComparisonModal', () => {
  const onClose = vi.fn();

  it('returns null when isOpen is false', () => {
    const { container } = render(
      <CaseComparisonModal isOpen={false} onClose={onClose} data={null} loading={false} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('shows loading spinner when loading', () => {
    const { container } = render(
      <CaseComparisonModal isOpen={true} onClose={onClose} data={null} loading={true} />
    );
    // Should show some loading indicator (spinner animation or loading text)
    expect(container.innerHTML.length).toBeGreaterThan(0);
  });

  it('shows fallback text when data is null and not loading', () => {
    render(
      <CaseComparisonModal isOpen={true} onClose={onClose} data={null} loading={false} />
    );
    expect(screen.getByText(/no comparison/i)).toBeInTheDocument();
  });

  it('renders analysis when data is provided', () => {
    const data = {
      case_name: 'Smith v. Jones',
      strength_rating: 'strong',
      documents_searched: 5,
      confidence_score: 0.92,
      key_holdings: ['The court held that...'],
      applicability_analysis: 'Directly applicable',
      supporting_points: ['Point 1'],
      distinguishing_factors: ['Point 2'],
      recommendation: 'Use this case as primary authority',
    };
    render(
      <CaseComparisonModal isOpen={true} onClose={onClose} data={data} loading={false} />
    );
    expect(screen.getByText(/Smith v. Jones/i)).toBeInTheDocument();
    expect(screen.getByText(/strong/i)).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    render(
      <CaseComparisonModal isOpen={true} onClose={onClose} data={null} loading={false} />
    );
    const buttons = screen.getAllByRole('button');
    const closeBtn = buttons[0];
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });
});
