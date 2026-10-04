import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { renderWithAppContext } from '../test/helpers';
import ResearchContext from '../contexts/ResearchContext';
import type { ResearchState } from '../hooks/useResearchState';
import { useAuthStore } from '../stores/authStore';
import ResearchView from './ResearchView';

function researchState(overrides: Record<string, unknown> = {}): ResearchState {
  return {
    messages: [],
    isProcessing: false,
    processingStage: '',
    lastMessageRef: { current: null },
    inputRef: { current: null },
    inputValue: '',
    setInputValue: vi.fn(),
    handleSend: vi.fn(),
    selectedCitation: null,
    setSelectedCitation: vi.fn(),
    includeCaseLaw: true,
    setIncludeCaseLaw: vi.fn(),
    includeMyDocs: true,
    setIncludeMyDocs: vi.fn(),
    mainDocFilter: null,
    setMainDocFilter: vi.fn(),
    openDocs: [],
    openDocument: vi.fn(),
    closeDocument: vi.fn(),
    docAnnotations: {},
    ...overrides,
  } as unknown as ResearchState;
}

function renderView(state: ResearchState) {
  return renderWithAppContext(
    <MemoryRouter initialEntries={['/research']}>
      <ResearchContext.Provider value={state}>
        <ResearchView />
      </ResearchContext.Provider>
    </MemoryRouter>,
    { fileInputRef: { current: null } },
  );
}

describe('ResearchView', () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: true });
  });

  it('renders empty state when no messages', () => {
    renderView(researchState());
    expect(screen.getByText('Matter Strategy')).toBeInTheDocument();
  });

  it('renders user messages', () => {
    const state = researchState({
      messages: [
        { id: '1', type: 'user', content: 'What is res judicata?' },
      ],
    });
    renderView(state);
    expect(screen.getByText('What is res judicata?')).toBeInTheDocument();
  });

  it('shows processing indicator', () => {
    const state = researchState({ isProcessing: true, processingStage: 'Searching...' });
    renderView(state);
    expect(screen.getByText(/Searching/)).toBeInTheDocument();
  });

  it('renders without crashing when authenticated', () => {
    const { container } = renderView(researchState());
    expect(container).toBeTruthy();
  });
});
