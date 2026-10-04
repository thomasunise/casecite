import { createContext, useContext } from 'react';

/**
 * Minimal AppContext — only provides the shared file input ref.
 * All other state has been migrated to Zustand stores or feature contexts.
 */
export interface AppContextValue {
  fileInputRef: React.RefObject<HTMLInputElement>;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppContext.Provider');
  return ctx;
}

export default AppContext;
