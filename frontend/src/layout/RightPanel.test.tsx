import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ResearchContext from '../contexts/ResearchContext';
import type { ResearchState } from '../hooks/useResearchState';
import { useUIStore } from '../stores/uiStore';

import RightPanel from './RightPanel';

// RightPanel reads collapse/tab state from the UI store and citations/history
// from ResearchContext.
function researchState(overrides: Record<string, unknown> = {}): ResearchState {
  return {
    allCitations: [],
    setSelectedCitation: vi.fn(),
    chatSessions: [],
    isLoadingSessions: false,
    currentSessionId: null,
    loadSession: vi.fn(),
    deleteSession: vi.fn(),
    handleClearSession: vi.fn(),
    ...overrides,
  } as unknown as ResearchState;
}

function renderPanel(overrides: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter>
      <ResearchContext.Provider value={researchState(overrides)}>
        <RightPanel />
      </ResearchContext.Provider>
    </MemoryRouter>,
  );
}

describe('RightPanel', () => {
  beforeEach(() => {
    useUIStore.setState({ rightSidebarCollapsed: false, rightPanelTab: 'sources' });
  });

  it('renders without crashing', () => {
    const { container } = renderPanel();
    expect(container).toBeTruthy();
  });

  it('contains buttons for interaction', () => {
    const { container } = renderPanel();
    expect(container.querySelector('button')).toBeTruthy();
  });

  it('renders collapsed state', () => {
    useUIStore.setState({ rightSidebarCollapsed: true });
    const { container } = renderPanel();
    expect(container.querySelector('[class*="ollapsed"]')).toBeTruthy();
  });
});
