import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useCaseViewStore } from '../stores/caseViewStore';
import type { CaseInfo } from '../types';
import CaseView from './CaseView';

// CaseView reads its state from the case view store.
describe('CaseView', () => {
  beforeEach(() => {
    useCaseViewStore.setState({
      mainViewCase: null,
      caseLoading: false,
      caseMessages: [],
      caseQueryInput: '',
      caseQueryLoading: false,
      showCaseDocSelector: false,
    });
  });

  it('renders without crashing', () => {
    const { container } = render(<CaseView />);
    expect(container).toBeTruthy();
  });

  it('shows back button', () => {
    render(<CaseView />);
    expect(screen.getByLabelText(/back/i)).toBeInTheDocument();
  });

  it('shows loading state', () => {
    useCaseViewStore.setState({ caseLoading: true });
    render(<CaseView />);
    expect(screen.getByText(/Loading case details/)).toBeInTheDocument();
  });

  it('renders case data when provided', () => {
    useCaseViewStore.setState({
      mainViewCase: {
        id: 'case-1',
        name: 'Smith v. Jones',
        case_name: 'Smith v. Jones',
        citation: '123 F.3d 456',
        court: 'ca9',
      } as unknown as CaseInfo,
    });
    render(<CaseView />);
    expect(screen.getByText(/Smith v. Jones/)).toBeInTheDocument();
  });
});
