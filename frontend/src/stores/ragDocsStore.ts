import { create } from 'zustand';
import { api } from '../api';
import { useUIStore } from './uiStore';
import { registerReset } from './resetRegistry';
import logger from '../utils/logger';
import type { RagDocument } from '../types';

export interface RagDocsState {
  ragDocs: RagDocument[];
  ragDocsLoading: boolean;
  ragDocsDeleting: Record<string, boolean>;
  ragDocsSearchQuery: string;
  setRagDocsSearchQuery: (val: string) => void;
  ragDocsFiltered: RagDocument[];
  _initialized: boolean;
  init: () => void;
  loadRagDocuments: () => Promise<void>;
  handleRagDocDelete: (doc: RagDocument) => void;
  // Folders
  folders: string[];
  loadFolders: () => Promise<void>;
  createFolder: (name: string) => Promise<void>;
  deleteFolder: (path: string) => Promise<void>;
  moveDocToFolder: (docId: string, folderPath: string | null) => Promise<void>;
}

export const useRagDocsStore = create<RagDocsState>((set, get) => ({
  ragDocs: [],
  ragDocsLoading: false,
  ragDocsDeleting: {},
  ragDocsSearchQuery: '',
  setRagDocsSearchQuery: (val) => {
    set({ ragDocsSearchQuery: val });
    // Recompute filtered
    const { ragDocs } = get();
    set({
      ragDocsFiltered: ragDocs.filter((d) =>
        !val || d.filename?.toLowerCase().includes(val.toLowerCase())
      ),
    });
  },
  ragDocsFiltered: [],

  _initialized: false,
  // Lazy first load, called from the view's useEffect — the list must appear
  // when the Knowledge Base opens, not only after a manual Refresh click.
  init: () => {
    if (get()._initialized) return;
    set({ _initialized: true });
    get().loadRagDocuments();
  },

  loadRagDocuments: async () => {
    set({ ragDocsLoading: true });
    try {
      const resp = await api.getDocuments();
      const docs = resp.documents || [];
      const { ragDocsSearchQuery } = get();
      set({
        ragDocs: docs,
        ragDocsFiltered: docs.filter((d) =>
          !ragDocsSearchQuery || d.filename?.toLowerCase().includes(ragDocsSearchQuery.toLowerCase())
        ),
      });
    } catch (err: unknown) {
      logger.error('Failed to load documents:', err);
      // Otherwise the Knowledge Base just looks empty.
      useUIStore.getState().addToast(`Could not load documents: ${(err as Error).message}`, 'error');
    } finally {
      set({ ragDocsLoading: false });
    }
    get().loadFolders();
  },

  // ── Folders ──────────────────────────────────────────────────────
  folders: [],

  loadFolders: async () => {
    try {
      const resp = await api.listFolders();
      set({ folders: resp.folders || [] });
    } catch (err: unknown) {
      logger.error('Failed to load folders:', err);
      useUIStore.getState().addToast(`Could not load folders: ${(err as Error).message}`, 'error');
    }
  },

  createFolder: async (name) => {
    try {
      const resp = await api.createFolder(name);
      set({ folders: resp.folders || [] });
      useUIStore.getState().addToast(`Folder created`, 'success');
    } catch (err: unknown) {
      useUIStore.getState().addToast(`Failed to create folder: ${(err as Error).message}`, 'error');
    }
  },

  deleteFolder: async (path) => {
    const doDelete = async () => {
      try {
        const resp = await api.deleteFolder(path);
        // Folder removed; any docs in it return to General locally.
        set((state) => {
          const cleared = state.ragDocs.map((d) =>
            d.folder_path && (d.folder_path === path || d.folder_path.startsWith(path + '/'))
              ? { ...d, folder_path: null }
              : d
          );
          return { folders: resp.folders || [], ragDocs: cleared, ragDocsFiltered: cleared };
        });
      } catch (err: unknown) {
        useUIStore.getState().addToast(`Failed to delete folder: ${(err as Error).message}`, 'error');
      }
    };
    useUIStore.getState().showConfirm({
      title: 'Delete Folder',
      message: `Delete folder "${path}"? Documents inside it move back to General.`,
      type: 'warning',
      confirmText: 'Delete',
      onConfirm: doDelete,
    });
  },

  moveDocToFolder: async (docId, folderPath) => {
    // Optimistic local update, then persist.
    set((state) => {
      const updated = state.ragDocs.map((d) =>
        d.id === docId ? { ...d, folder_path: folderPath } : d
      );
      return {
        ragDocs: updated,
        ragDocsFiltered: updated.filter((d) =>
          !state.ragDocsSearchQuery || d.filename?.toLowerCase().includes(state.ragDocsSearchQuery.toLowerCase())
        ),
      };
    });
    try {
      await api.moveDocument(docId, folderPath);
    } catch (err: unknown) {
      useUIStore.getState().addToast(`Failed to move document: ${(err as Error).message}`, 'error');
      get().loadRagDocuments();
    }
  },

  handleRagDocDelete: (doc) => {
    const doDelete = async () => {
      set((state) => ({ ragDocsDeleting: { ...state.ragDocsDeleting, [doc.id]: true } }));
      try {
        await api.deleteDocument(doc.id);
        set((state) => {
          const newDocs = state.ragDocs.filter((d) => d.id !== doc.id);
          return {
            ragDocs: newDocs,
            ragDocsFiltered: newDocs.filter((d) =>
              !state.ragDocsSearchQuery || d.filename?.toLowerCase().includes(state.ragDocsSearchQuery.toLowerCase())
            ),
          };
        });
        useUIStore.getState().addToast(`Deleted ${doc.filename}`, 'success');
      } catch (err: unknown) {
        logger.error('Delete error:', err);
        useUIStore.getState().addToast(`Failed to delete: ${(err as Error).message}`, 'error');
      } finally {
        set((state) => {
          const next = { ...state.ragDocsDeleting };
          delete next[doc.id];
          return { ragDocsDeleting: next };
        });
      }
    };
    useUIStore.getState().showConfirm({
      title: 'Delete Document',
      message: `Delete "${doc.filename}"? The file, its indexed text, and any contract analyses or citation maps built from it are permanently deleted.`,
      type: 'danger',
      confirmText: 'Delete',
      onConfirm: doDelete,
    });
  },
}));

registerReset(() => useRagDocsStore.setState(useRagDocsStore.getInitialState(), true));
