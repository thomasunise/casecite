import { useEffect } from 'react';
import { api, API_BASE_URL } from '../api';
import { useAuthStore } from '../stores/authStore';
import { useBrandingStore } from '../stores/brandingStore';
import { useSettingsStore } from '../stores/settingsStore';
import { useUIStore } from '../stores/uiStore';
import { RAG_SETTINGS_KEY, migrateLegacyStorage } from '../utils/storageKeys';
import type { UserInfo } from '../api/types';
import type { ChatMessage, RagSettings, SystemStats } from '../types';
import logger from '../utils/logger';

/**
 * Orchestrates all App-level side effects:
 *  - Mount-time bootstrap (theme, branding, CSRF, session probe, health)
 *  - Per-sign-in data loading (server settings, document counts, connectors)
 *  - Scroll-to-newest on new messages
 *  - localStorage persistence for RAG settings
 *  - Enter-key-to-send binding
 */
export function useAppEffects({
  setUser, setIsAuthenticated, loadConnectors,
  setSystemStats,
  messages, lastMessageRef, ragSettings, inputRef, handleSend,
}: {
  setUser: (user: UserInfo | null) => void;
  setIsAuthenticated: (val: boolean) => void;
  loadConnectors: () => Promise<void>;
  setSystemStats: (stats: SystemStats | ((prev: SystemStats) => SystemStats)) => void;
  messages: ChatMessage[];
  lastMessageRef: React.RefObject<HTMLDivElement | null>;
  ragSettings: RagSettings;
  inputRef: React.RefObject<HTMLElement | null>;
  handleSend: () => void;
}) {
  const isAuthenticated = useAuthStore((st) => st.isAuthenticated);
  const mustChangePassword = useAuthStore((st) => !!st.user?.must_change_password);
  const mfaEnrollmentRequired = useAuthStore((st) => !!st.user?.mfa_enrollment_required);

  // ==================== MOUNT-TIME BOOTSTRAP ====================
  useEffect(() => {
    const bootstrap = async () => {
      // Apply the saved theme and branding early so the app is styled before auth
      useUIStore.getState().initTheme();
      useBrandingStore.getState().loadBranding();
      // Hydrate persisted RAG settings synchronously, BEFORE the persistence
      // effect below can write the in-memory defaults back to localStorage.
      migrateLegacyStorage();
      useSettingsStore.getState().init();

      await api.initCsrf();

      // Try to authenticate via httpOnly cookie (no localStorage token needed)
      try {
        const userData = await api.getCurrentUser();
        setUser(userData);
        setIsAuthenticated(true);
      } catch {
        logger.debug('Not authenticated or token expired');
      }

      // The public health status needs no credentials. Anything other than an
      // explicit "healthy" — including a failed request — is shown as such.
      try {
        const healthUrl = `${API_BASE_URL.replace('/api/v1', '')}/health`;
        const response = await fetch(healthUrl, { credentials: 'include' });
        const health = response.ok ? await response.json() : null;
        setSystemStats((prev) => ({ ...prev, isHealthy: health?.status === 'healthy' }));
      } catch (e) {
        logger.debug('Could not load health stats:', e instanceof Error ? e.message : String(e));
        setSystemStats((prev) => ({ ...prev, isHealthy: false }));
      }
    };

    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only bootstrap
  }, []);

  // ==================== PER-SIGN-IN DATA ====================
  // Runs whenever a session starts — page load with a live cookie, a login,
  // a signup, or an MFA verification — not only at mount. Loading settings
  // only at mount left a freshly signed-in user on the defaults, and the next
  // "Save" overwrote their stored playbook, profile and prompts with blanks.
  useEffect(() => {
    if (!isAuthenticated) return;
    // An account that still has to replace a temporary password or enrol in
    // required two-factor auth is refused everything else; these loads run
    // once that is done.
    if (mustChangePassword || mfaEnrollmentRequired) return;
    const settings = useSettingsStore.getState();
    settings.loadServerSettings();
    // Document counts come from the documents API, not /health.
    settings.refreshSystemStats();
    loadConnectors();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only on auth flips; loader identity is unstable
  }, [isAuthenticated, mustChangePassword, mfaEnrollmentRequired]);

  // ==================== REQUIRED MFA ENROLLMENT ====================
  // The firm requires two-factor authentication and this account has none:
  // take the user straight to the setup screen (after any forced password
  // change — that dialog comes first).
  useEffect(() => {
    if (!isAuthenticated || mustChangePassword || !mfaEnrollmentRequired) return;
    const ui = useUIStore.getState();
    ui.openSettings('security');
    ui.addToast('Your firm requires two-factor authentication. Set it up to continue.', 'warning');
  }, [isAuthenticated, mustChangePassword, mfaEnrollmentRequired]);

  // ==================== SCROLL TO NEWEST MESSAGE ====================
  // Land at the TOP of the newest message, never the bottom of the thread —
  // long answers must read from their first line.
  useEffect(() => {
    lastMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ref identity is stable; scroll only on new messages
  }, [messages]);

  // ==================== LOCALSTORAGE PERSISTENCE ====================
  // Citations are deliberately NOT persisted: the Sources panel is per-search.
  // Search history lives server-side as chat sessions.
  useEffect(() => {
    try {
      localStorage.setItem(RAG_SETTINGS_KEY, JSON.stringify(ragSettings));
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
