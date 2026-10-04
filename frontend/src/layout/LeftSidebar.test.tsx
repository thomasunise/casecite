import { describe, it, expect, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { renderWithAppContext } from '../test/helpers';
import { useUIStore } from '../stores/uiStore';
import { useAuthStore } from '../stores/authStore';
import { useDocumentsStore } from '../stores/documentsStore';

// LeftSidebar is a default export
import LeftSidebar from './LeftSidebar';

// LeftSidebar reads state from zustand stores and react-router;
// AppContext only supplies fileInputRef.
function renderSidebar() {
  return renderWithAppContext(
    <MemoryRouter initialEntries={['/research']}>
      <LeftSidebar />
    </MemoryRouter>,
    { fileInputRef: { current: null } },
  );
}

describe('LeftSidebar', () => {
  beforeEach(() => {
    useUIStore.setState({ leftSidebarCollapsed: false });
    useAuthStore.setState({ isAuthenticated: true });
    useDocumentsStore.setState({ documents: [] });
  });

  it('renders without crashing', () => {
    const { container } = renderSidebar();
    expect(container).toBeTruthy();
  });

  it('shows mode navigation items', () => {
    renderSidebar();
    expect(screen.getByText('Matter Strategy')).toBeInTheDocument();
    expect(screen.getByText('Contracts')).toBeInTheDocument();
    // Case Citations merged into Matter Strategy — no longer a sidebar mode.
    expect(screen.queryByText('Case Citations')).not.toBeInTheDocument();
  });

  it('shows collapse toggle', () => {
    renderSidebar();
    const toggle = screen.getByLabelText(/collapse|expand/i);
    expect(toggle).toBeInTheDocument();
  });

  it('toggles leftSidebarCollapsed in the UI store on toggle click', () => {
    renderSidebar();
    const toggle = screen.getByLabelText(/collapse sidebar/i);
    fireEvent.click(toggle);
    expect(useUIStore.getState().leftSidebarCollapsed).toBe(true);
  });
});
