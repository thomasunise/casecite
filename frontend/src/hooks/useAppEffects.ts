import { useEffect } from 'react';
import { api, API_BASE_URL } from '../api';
import { useBrandingStore } from '../stores/brandingStore';
import { useSettingsStore } from '../stores/settingsStore';
import { useUIStore } from '../stores/uiStore';
import type { UserInfo } from '../api/types';
import type { ChatMessage, RagSettings, SystemStats } from '../types';
import logger from '../utils/logger';

/**
 * Orchestrates all App-level side effects:
 *  - Initial data loading (CSRF, auth check, connectors, health, RAG settings)
 *  - Scroll-to-bottom on new messages
 *  - localStorage persistence for RAG settings
 *  - Enter-key-to-send binding
 */
export function useAppEffects({
  setUser, setIsAuthenticated, loadConnectors,
  setSystemStats, setRagSettings,
  messages, lastMessageRef, ragSettings, inputRef, handleSend,
}: {
  setUser: (user: UserInfo | null) => void;
  setIsAuthenticated: (val: boolean) => void;
  loadConnectors: () => Promise<void>;
  setSystemStats: (stats: SystemStats | ((prev: SystemStats) => SystemStats)) => void;
  setRagSettings: (settings: RagSettings) => void;
  messages: ChatMessage[];
  lastMessageRef: React.RefObject<HTMLDivElement | null>;
  ragSettings: RagSettings;
  inputRef: React.RefObject<HTMLElement | null>;
  handleSend: () => void;
}) {
  // ==================== LOAD INITIAL DATA ====================
  useEffect(() => {
    const loadInitialData = async () => {
      // Apply the saved theme and branding early so the app is styled before auth
      useUIStore.getState().initTheme();
      useBrandingStore.getState().loadBranding();
      // Hydrate persisted RAG settings synchronously, BEFORE the persistence
      // effect below can write the in-memory defaults back to localStorage.
      useSettingsStore.getState().init();

      await api.initCsrf();

      try {
        // Try to authenticate via httpOnly cookie (no localStorage token needed)
        try {
          const userData = await api.getCurrentUser();
          setUser(userData);
          setIsAuthenticated(true);
        } catch {
          logger.debug('Not authenticated or token expired');
        }

        await loadConnectors();

        try {
          const healthUrl = `${API_BASE_URL.replace('/api/v1', '')}/health`;
          const response = await api.authFetch(healthUrl);
          if (response.ok) {
            const health = await response.json();
            setSystemStats((prev) => ({ ...prev, isHealthy: health.status === 'healthy' }));
          }
        } catch (e) {
          logger.debug('Could not load health stats:', e instanceof Error ? e.message : String(e));
        }
        // Document counts come from the documents API, not /health (which no
        // longer carries per-user stats — the old code left the pill at 0).
        useSettingsStore.getState().refreshSystemStats();

        try {
          const serverSettings = await api.getSettings();
          if (serverSettings) {
            const mappedSettings = {
              vectorDb: serverSettings.vector_db || 'chroma',
              indexName: serverSettings.index_name || 'casecite-legal-docs',
              embeddingModel: serverSettings.embedding_model || 'text-embedding-3-small',
              dimensions: serverSettings.dimensions || 1536,
              chunkSize: serverSettings.chunk_size || 512,
              chunkOverlap: serverSettings.chunk_overlap || 128,
              similarityThreshold: serverSettings.similarity_threshold || 0.25,
              topK: serverSettings.top_k || 10,
              enableReranking: serverSettings.enable_reranking !== false,
              hybridSearch: serverSettings.hybrid_search !== false,
              citationVerification: serverSettings.citation_verification !== false,
              contextCompression: serverSettings.context_compression || false,
              queryExpansion: serverSettings.query_expansion !== false,
              sourceTracking: serverSettings.source_tracking !== false,
              llmModel: serverSettings.llm_model || 'gpt-5.5',
              temperature: serverSettings.temperature || 0.1,
              maxTokens: serverSettings.max_tokens || 4096,
              batchSize: 100,
              contract_playbook: serverSettings.contract_playbook ?? null,
              practice_area: serverSettings.practice_area ?? null,
              practice_profile: serverSettings.practice_profile ?? null,
              custom_system_prompt: serverSettings.custom_system_prompt ?? null,
              custom_grounding_rules: serverSettings.custom_grounding_rules ?? null,
              custom_factual_prompt: serverSettings.custom_factual_prompt ?? null,
              custom_research_prompt: serverSettings.custom_research_prompt ?? null,
              custom_case_prompt: serverSettings.custom_case_prompt ?? null,
              custom_document_prompt: serverSettings.custom_document_prompt ?? null,
              custom_compliance_prompt: serverSettings.custom_compliance_prompt ?? null,
              custom_strategy_prompt: serverSettings.custom_strategy_prompt ?? null,
            };
            setRagSettings({ ...ragSettings, ...mappedSettings } as RagSettings);
            logger.debug('Loaded RAG settings from backend');
          }
        } catch (e) {
          logger.debug('Could not load RAG settings from backend, using local:', e instanceof Error ? e.message : String(e));
        }
      } catch (error) {
        logger.error('Error loading initial data:', error);
      }
    };

    loadInitialData();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only bootstrap
  }, []);

  // ==================== SCROLL TO NEWEST MESSAGE ====================
  // Land at the TOP of the newest message, never the bottom of the thread —
  // long answers must read from their first line.
  useEffect(() => {
    lastMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ref identity is stable; scroll only on new messages
  }, [messages]);

  // ==================== LOCALSTORAGE PERSISTENCE ====================
  // Citations are deliberately NOT persisted: the Sources panel is per-search.
  // Persisting them resurrected citations from long-dead sessions ("phantom
  // sources") on every page load. Search history now lives server-side as
  // chat sessions. Purge both legacy keys once.
  useEffect(() => {
    try {
      localStorage.removeItem('wl_citations');
      localStorage.removeItem('wl_search_history');
    } catch (e) { logger.warn('Failed to purge legacy storage:', e); }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('wl_rag_settings', JSON.stringify(ragSettings));
    } catch (e) { logger.warn('Failed to save RAG settings:', e); }
  }, [ragSettings]);

  // ==================== ENTER KEY TO SEND ====================
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey && document.activeElement === inputRef.current) {
        e.preventDefault();
        handleSend();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleSend, inputRef]);
}
