import logger from './logger';

/** localStorage keys owned by the app. */
export const RAG_SETTINGS_KEY = 'casecite_rag_settings';

// Keys written by earlier builds under the previous product prefix.
const LEGACY_RAG_SETTINGS_KEY = 'wl_rag_settings';
const LEGACY_PURGE_KEYS = ['wl_citations', 'wl_search_history'];

/**
 * One-time move of values stored under the old prefix. Settings carry over to
 * the new key; citations and search history are dropped (they now live
 * server-side, and persisting them resurrected sources from dead sessions).
 * Safe to call repeatedly — it is a no-op once the old keys are gone.
 */
export function migrateLegacyStorage(): void {
  try {
    const legacy = localStorage.getItem(LEGACY_RAG_SETTINGS_KEY);
    if (legacy !== null) {
      if (localStorage.getItem(RAG_SETTINGS_KEY) === null) {
        localStorage.setItem(RAG_SETTINGS_KEY, legacy);
      }
      localStorage.removeItem(LEGACY_RAG_SETTINGS_KEY);
    }
    for (const key of LEGACY_PURGE_KEYS) localStorage.removeItem(key);
  } catch (e) {
    logger.warn('Could not migrate legacy storage keys:', e);
  }
}

/** Remove locally cached settings (they include confidential work product). */
export function clearStoredRagSettings(): void {
  try {
    localStorage.removeItem(RAG_SETTINGS_KEY);
    localStorage.removeItem(LEGACY_RAG_SETTINGS_KEY);
  } catch { /* storage unavailable — nothing to clear */ }
}
