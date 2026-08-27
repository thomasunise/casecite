import { create } from 'zustand';
import { api } from '../api';
import { useUIStore } from './uiStore';
import { registerReset } from './resetRegistry';
import logger from '../utils/logger';
import type { CaseInfo, CaseComparisonData, DocumentFilter } from '../types';

export interface CaseComparisonState {
  showCaseComparison: boolean;
  setShowCaseComparison: (val: boolean) => void;
  caseComparisonData: CaseComparisonData | null;
  caseComparisonLoading: boolean;
  showCompareDocSelector: boolean;
  setShowCompareDocSelector: (val: boolean) => void;
  compareDocFilter: DocumentFilter | null;
  pendingCompareCase: CaseInfo | null;
  setPendingCompareCase: (val: CaseInfo | null) => void;
  executeComparison: (docFilter: DocumentFilter | null) => Promise<void>;
}

export const useCaseComparisonStore = create<CaseComparisonState>((set, get) => ({
  showCaseComparison: false,
  setShowCaseComparison: (val) => set({ showCaseComparison: val }),
  caseComparisonData: null,
  caseComparisonLoading: false,
  showCompareDocSelector: false,
  setShowCompareDocSelector: (val) => set({ showCompareDocSelector: val }),
  compareDocFilter: null,
  pendingCompareCase: null,
  setPendingCompareCase: (val) => set({ pendingCompareCase: val }),

  executeComparison: async (docFilter) => {
    const { pendingCompareCase } = get();
    if (!pendingCompareCase) return;

    set({
      showCompareDocSelector: false,
      caseComparisonLoading: true,
      showCaseComparison: true,
      caseComparisonData: null,
    });

    try {
      const result = await api.compareCaseToDocuments(
        pendingCompareCase.id,
        pendingCompareCase.case_name || pendingCompareCase.name,
        (pendingCompareCase.citations?.[0] as string) || '',
        pendingCompareCase.opinion_text || pendingCompareCase.plain_text || '',
        docFilter ? { ...docFilter } : null,
      );
      set({ caseComparisonData: result });
    } catch (error: unknown) {
      logger.error('Comparison failed:', error);
      useUIStore.getState().addToast('Failed to compare case: ' + (error instanceof Error ? error.message : String(error)), 'error');
      set({ showCaseComparison: false });
    } finally {
      set({ caseComparisonLoading: false, pendingCompareCase: null });
    }
  },
}));

registerReset(() => useCaseComparisonStore.setState(useCaseComparisonStore.getInitialState(), true));
