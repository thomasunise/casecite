import { create } from 'zustand';
import { registerReset } from './resetRegistry';
import { api } from '../api';
import { appNavigate } from '../utils/router';
import logger from '../utils/logger';
import type { WorkspaceSessionSummary } from '../api/types';

/**
 * Universal History. Every surface autosaves its working session here as a
 * snapshot (debounced upsert), and clicking a session in the History panel
 * rehydrates that surface exactly — the tool results, the conversation, the
 * drafted contract, all of it.
 */

interface WorkspaceSessionsState {
  sessions: WorkspaceSessionSummary[];
  loading: boolean;
  restoringId: string | null;
  _initialized: boolean;
  init: () => void;
  loadSessions: () => Promise<void>;
  /** Debounced upsert. `key` binds ongoing work to one row; resetKey(key)
      makes the next save create a NEW session (fresh conversation). */
  saveSession: (key: string, surface: string, title: string, payload: Record<string, unknown>) => void;
  resetKey: (key: string) => void;
  deleteSession: (id: string) => Promise<void>;
  restoreSession: (id: string) => Promise<void>;
}

const boundIds: Record<string, string> = {};
const timers: Record<string, ReturnType<typeof setTimeout>> = {};
const SAVE_DEBOUNCE_MS = 1500;

export const useWorkspaceSessionsStore = create<WorkspaceSessionsState>((set, get) => ({
  sessions: [],
  loading: false,
  restoringId: null,
  _initialized: false,

  init: () => {
    if (get()._initialized) return;
    set({ _initialized: true });
    void get().loadSessions();
  },

  loadSessions: async () => {
    set({ loading: true });
    try {
      const res = await api.listWorkspaceSessions();
      set({ sessions: res.sessions });
    } catch (e) {
      logger.error('workspace sessions load failed', e);
    }
    set({ loading: false });
  },

  saveSession: (key, surface, title, payload) => {
    if (timers[key]) clearTimeout(timers[key]);
    timers[key] = setTimeout(async () => {
      delete timers[key];
      try {
        const boundId = boundIds[key];
        const row = boundId
          ? await api.updateWorkspaceSession(boundId, { title, payload })
          : await api.createWorkspaceSession(surface, title, payload);
        boundIds[key] = row.id;
        set((st) => ({
          sessions: [row, ...st.sessions.filter((s) => s.id !== row.id)],
        }));
      } catch (e) {
        // A 404 means the bound row was deleted from History — rebind fresh.
        if (boundIds[key] && e instanceof Error && /not found/i.test(e.message)) {
          delete boundIds[key];
        }
        logger.error('workspace session save failed', e);
      }
    }, SAVE_DEBOUNCE_MS);
  },

  resetKey: (key) => {
    delete boundIds[key];
    if (timers[key]) { clearTimeout(timers[key]); delete timers[key]; }
  },

  deleteSession: async (id) => {
    try {
      await api.deleteWorkspaceSession(id);
      set((st) => ({ sessions: st.sessions.filter((s) => s.id !== id) }));
      for (const [key, bound] of Object.entries(boundIds)) {
        if (bound === id) delete boundIds[key];
      }
    } catch (e) {
      logger.error('workspace session delete failed', e);
    }
  },

  restoreSession: async (id) => {
    set({ restoringId: id });
    try {
      const detail = await api.getWorkspaceSession(id);
      const payload = detail.payload || {};
      // Rebind ongoing autosaves to the restored row so continuing the
      // session updates it instead of forking a duplicate.
      if (detail.surface === 'contracts') {
        boundIds['contracts'] = id;
        const { useContractsStore } = await import('./contractsStore');
        await useContractsStore.getState().restoreWorkspaceSession(payload);
        appNavigate('/contracts');
      } else if (detail.surface.startsWith('tool:')) {
        const toolId = detail.surface.slice('tool:'.length);
        boundIds[detail.surface] = id;
        const { useToolsStore } = await import('./toolsStore');
        useToolsStore.getState().restoreWorkspaceSession(toolId, payload);
        appNavigate(`/tools/${toolId}`);
      } else if (detail.surface === 'drafting') {
        boundIds['drafting'] = id;
        const { useDraftingStore } = await import('./draftingStore');
        await useDraftingStore.getState().restoreWorkspaceSession(payload);
        appNavigate('/drafting');
      } else if (detail.surface === 'judge') {
        boundIds['judge'] = id;
        const { useJudgeIntelStore } = await import('./judgeIntelStore');
        await useJudgeIntelStore.getState().restoreWorkspaceSession(payload);
        appNavigate('/judge-intel');
      } else if (detail.surface === 'case') {
        boundIds['case'] = id;
        const { useCaseViewStore } = await import('./caseViewStore');
        await useCaseViewStore.getState().restoreWorkspaceSession(payload);
      } else {
        logger.error(`unknown session surface: ${detail.surface}`);
      }
    } catch (e) {
      logger.error('workspace session restore failed', e);
      try {
        const { useUIStore } = await import('./uiStore');
        useUIStore.getState().addToast('Could not restore that session.', 'error');
      } catch { /* noop */ }
    }
    set({ restoringId: null });
  },
}));

/** Fire-and-forget autosave helper for the surface stores. */
export function persistWorkspaceSession(
  key: string,
  surface: string,
  title: string,
  payload: Record<string, unknown>,
): void {
  try {
    useWorkspaceSessionsStore.getState().saveSession(key, surface, title, payload);
  } catch (e) {
    logger.error('workspace session persist failed', e);
  }
}

/** Fresh conversation → the next save creates a new History row. */
export function resetWorkspaceSessionKey(key: string): void {
  try {
    useWorkspaceSessionsStore.getState().resetKey(key);
  } catch { /* noop */ }
}

// Sign-out: drop pending autosaves and the key→row bindings so the next
// user's work never lands in this user's History rows.
registerReset(() => {
  for (const key of Object.keys(timers)) { clearTimeout(timers[key]); delete timers[key]; }
  for (const key of Object.keys(boundIds)) delete boundIds[key];
  useWorkspaceSessionsStore.setState(useWorkspaceSessionsStore.getInitialState(), true);
});
