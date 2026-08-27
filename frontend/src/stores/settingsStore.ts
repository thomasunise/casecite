import { create } from 'zustand';
import { api } from '../api';
import logger from '../utils/logger';
import { useUIStore } from './uiStore';
import { registerReset } from './resetRegistry';
import type { RagSettings, SystemStats } from '../types';

const defaultRagSettings = {
  vectorDb: 'chroma', indexName: 'casecite-legal-docs', embeddingModel: 'text-embedding-3-small',
  // 0.25: text-embedding-3 similarities run low (relevant ≈ 0.30-0.50) — a
  // higher floor silently discards real matches.
  dimensions: 1536, chunkSize: 512, chunkOverlap: 128, similarityThreshold: 0.25,
  topK: 10, enableReranking: true, hybridSearch: true, citationVerification: true,
  contextCompression: false, queryExpansion: true, sourceTracking: true,
  llmModel: 'gpt-5.5', temperature: 0.1, maxTokens: 16384, batchSize: 100,
};

export function loadSavedRagSettings() {
  try {
    const saved = localStorage.getItem('wl_rag_settings');
    if (saved) {
      const parsed = JSON.parse(saved);
      return { ...defaultRagSettings, ...parsed };
    }
  } catch (e) { logger.debug('Could not load RAG settings from localStorage:', e); }
  return defaultRagSettings;
}

export interface SettingsState {
  _initialized: boolean;
  /** Hydrate persisted settings from localStorage (lazy — never at import time). */
  init: () => void;
  ragSettings: RagSettings;
  setRagSettings: (settings: RagSettings) => void;
  systemStats: SystemStats;
  setSystemStats: (stats: SystemStats | ((prev: SystemStats) => SystemStats)) => void;
  isReindexing: boolean;
  setIsReindexing: (val: boolean) => void;
  isClearing: boolean;
  setIsClearing: (val: boolean) => void;
  /** Resolves true when the server accepted the settings; false after a rollback. */
  handleSaveSettings: (newSettings: RagSettings) => Promise<boolean>;
  handleReindex: () => Promise<void>;
  refreshSystemStats: () => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set, _get) => ({
  _initialized: false,
  init: () => {
    if (_get()._initialized) return;
    set({ _initialized: true, ragSettings: loadSavedRagSettings() });
  },
  ragSettings: defaultRagSettings,
  setRagSettings: (settings) => set({ ragSettings: settings }),
  systemStats: { totalDocuments: 0, totalEmbeddings: 0, isHealthy: true },
  setSystemStats: (stats) => set((state) => ({ systemStats: typeof stats === 'function' ? stats(state.systemStats) : stats })),
  isReindexing: false,
  setIsReindexing: (val) => set({ isReindexing: val }),
  isClearing: false,
  setIsClearing: (val) => set({ isClearing: val }),

  // Optimistic: the new values apply immediately, but a failed save rolls
  // them back and tells the user — a silent failure left the modal's values
  // on screen while the server (and the next reload) still had the old ones.
  handleSaveSettings: async (newSettings) => {
    const previous = _get().ragSettings;
    set({ ragSettings: newSettings });
    try {
      await api.updateSettings({
        vector_db: newSettings.vectorDb,
        index_name: newSettings.indexName,
        embedding_model: newSettings.embeddingModel,
        dimensions: newSettings.dimensions,
        chunk_size: newSettings.chunkSize,
        chunk_overlap: newSettings.chunkOverlap,
        similarity_threshold: newSettings.similarityThreshold,
        top_k: newSettings.topK,
        enable_reranking: newSettings.enableReranking,
        hybrid_search: newSettings.hybridSearch,
        llm_model: newSettings.llmModel,
        temperature: newSettings.temperature,
        max_tokens: newSettings.maxTokens,
        contract_playbook: newSettings.contract_playbook ?? null,
        practice_area: newSettings.practice_area ?? null,
        practice_profile: newSettings.practice_profile ?? null,
        custom_system_prompt: newSettings.custom_system_prompt ?? null,
        custom_grounding_rules: newSettings.custom_grounding_rules ?? null,
        custom_factual_prompt: newSettings.custom_factual_prompt ?? null,
        custom_research_prompt: newSettings.custom_research_prompt ?? null,
        custom_case_prompt: newSettings.custom_case_prompt ?? null,
        custom_document_prompt: newSettings.custom_document_prompt ?? null,
        custom_compliance_prompt: newSettings.custom_compliance_prompt ?? null,
        custom_strategy_prompt: newSettings.custom_strategy_prompt ?? null,
      });
      logger.debug('Settings saved to backend');
      return true;
    } catch (error) {
      logger.error('Failed to save settings:', error);
      set({ ragSettings: previous });
      const message = error instanceof Error ? error.message : String(error);
      useUIStore.getState().addToast(`Could not save settings: ${message}`, 'error');
      return false;
    }
  },

  // The header pill's source of truth: the user's own document list. (It used
  // to read a stats field the health endpoint no longer returns, so it was
  // pinned at 0 forever.)
  refreshSystemStats: async () => {
    try {
      const resp = await api.getDocuments(200, 0);
      const docs = resp.documents || [];
      const indexed = docs.filter((d) => d.status === 'indexed');
      set((state) => ({
        systemStats: {
          ...state.systemStats,
          totalDocuments: indexed.length,
          totalEmbeddings: indexed.reduce(
            (n, d) => n + ((d.chunk_count as number) || 0), 0
          ),
        },
      }));
    } catch (error) {
      logger.debug('Could not refresh document stats:', error);
    }
  },

  handleReindex: async () => {
    const { addToast } = useUIStore.getState();
    set({ isReindexing: true });
    try {
      await api.reindexDocuments();
      addToast('Reindex complete', 'success');
    } catch (error) {
      logger.error('Reindex error:', error);
      addToast('Reindex failed', 'error');
    }
    set({ isReindexing: false });
    _get().refreshSystemStats();
  },
}));

// Sign-out wipes the in-memory copy (the playbook and practice profile are
// confidential work product) — the server remains the source of truth.
registerReset(() => useSettingsStore.setState(useSettingsStore.getInitialState(), true));
