import { create } from 'zustand';
import { registerReset } from './resetRegistry';

export interface DocumentsState {
  documents: Record<string, unknown>[];
  setDocuments: (docs: Record<string, unknown>[] | ((prev: Record<string, unknown>[]) => Record<string, unknown>[])) => void;
}

export const useDocumentsStore = create<DocumentsState>((set) => ({
  documents: [],
  setDocuments: (docs) => set((state) => ({
    documents: typeof docs === 'function' ? docs(state.documents) : docs,
  })),
}));

registerReset(() => useDocumentsStore.setState(useDocumentsStore.getInitialState(), true));
