import { createContext, useContext } from 'react';
import type { ResearchState } from '../hooks/useResearchState';

const ResearchContext = createContext<ResearchState | null>(null);

export function useResearch(): ResearchState {
  const ctx = useContext(ResearchContext);
  if (!ctx) throw new Error('useResearch must be used within ResearchContext.Provider');
  return ctx;
}

export default ResearchContext;
