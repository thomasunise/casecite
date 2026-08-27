import React from 'react';
import { render, RenderOptions } from '@testing-library/react';
import AppContext from '../contexts/AppContext';
import type { AppContextValue } from '../contexts/AppContext';

/**
 * Render a component wrapped in AppContext with the given value.
 * Any keys not provided default to no-op/empty values.
 */
export function renderWithAppContext(
  ui: React.ReactElement,
  contextOverrides: Record<string, unknown> = {},
  renderOptions: Omit<RenderOptions, 'wrapper'> = {},
) {
  const defaultCtx = {
    toasts: [],
    addToast: vi.fn(),
    user: null,
    isAuthenticated: false,
    ...contextOverrides,
  };

  function Wrapper({ children }: { children: React.ReactNode }) {
    return <AppContext.Provider value={defaultCtx as unknown as AppContextValue}>{children}</AppContext.Provider>;
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    ctx: defaultCtx,
  };
}
