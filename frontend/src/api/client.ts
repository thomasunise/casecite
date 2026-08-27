import { getCookie } from '../utils';
import type { ApiClient, RequestOptions } from './types';

// ==================== API CLIENT ====================
export const API_BASE_URL = import.meta.env.DEV
  ? 'http://localhost:8000/api/v1'
  : `${window.location.origin}/api/v1`;

// Endpoints where a 401 means "wrong credentials", not "expired session":
// no refresh attempt, and the server's own message is surfaced.
const CREDENTIAL_ENDPOINTS = new Set([
  '/auth/login',
  '/auth/register',
  '/auth/mfa/verify',
  '/auth/mfa/recovery',
  '/auth/demo/login',
  '/auth/azure/login',
]);

function isCredentialEndpoint(endpoint: string): boolean {
  const path = endpoint.split('?')[0];
  return CREDENTIAL_ENDPOINTS.has(path);
}

export const api = {
  token: null as string | null,

  setToken(token: string) {
    this.token = token;
    // Tokens are stored in httpOnly cookies by the backend (the refresh token
    // never reaches JS). Keep in-memory only for the Authorization header.
  },

  getToken(): string | null {
    return this.token;
  },

  async initCsrf() {
    // Fetch CSRF token on app load so the cookie is set before any POST requests
    try { await this.request('/csrf-token'); } catch { /* non-critical */ }
  },

  async request(endpoint: string, options: RequestOptions = {}) {
    const url = `${API_BASE_URL}${endpoint}`;

    const isFormData = options.body instanceof FormData;
    const method = (options.method || 'GET').toUpperCase();
    const csrfToken = getCookie('_csrf');
    const headers: Record<string, string> = {
      // Don't set Content-Type for FormData - browser sets it with boundary
      ...(!isFormData && { 'Content-Type': 'application/json' }),
      ...(this.getToken() && { 'Authorization': `Bearer ${this.getToken()}` }),
      // CSRF: Include token on state-changing requests
      ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method) && { 'X-CSRF-Token': csrfToken }),
      ...options.headers,
    };

    // Add request timeout (30s default) via AbortController
    const controller = new AbortController();
    const timeoutMs = options.timeout || 30000;
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    let response: Response;
    try {
      response = await fetch(url, { ...options, headers, credentials: 'include', signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }

    if (response.status === 401) {
      // A 401 from a credential endpoint means the credentials were wrong —
      // there is no session to refresh, and the server's message ("Invalid
      // email or password", "Invalid code") is the one the user needs.
      if (isCredentialEndpoint(endpoint)) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' && error.detail ? error.detail : 'Invalid credentials');
      }
      // Attempt one token refresh before giving up
      if (!options._retried) {
        const refreshed = await this.refreshAccessToken();
        if (refreshed) {
          return this.request(endpoint, { ...options, _retried: true });
        }
      }
      this.token = null;
      // The session is dead and unrefreshable (e.g. signing keys rotated by a
      // deploy). Never leave the UI in a zombie logged-in state — clear auth
      // and surface the login modal. Dynamic import avoids a module cycle.
      import('../stores/authStore').then(({ useAuthStore }) => {
        const auth = useAuthStore.getState();
        if (auth.isAuthenticated) {
          auth.setIsAuthenticated(false);
          auth.setShowLoginModal(true);
          // Whoever signs in next must not inherit this user's work.
          import('../stores/resetRegistry').then(({ resetAllStores }) => resetAllStores());
          import('../stores/uiStore').then(({ useUIStore }) => {
            useUIStore.getState().addToast('Your session expired — please sign in again.', 'warning');
          });
        }
      });
      throw new Error('Unauthorized - please log in');
    }

    if (response.status === 403) {
      const error = await response.json().catch(() => ({ detail: 'Forbidden' }));
      if (error.detail && typeof error.detail === 'string' && error.detail.includes('CSRF')) {
        throw new Error('Session expired. Please refresh the page.');
      }
      throw new Error(error.detail || 'Forbidden');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  },

  async refreshAccessToken(): Promise<boolean> {
    try {
      const csrfToken = getCookie('_csrf');
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrfToken && { 'X-CSRF-Token': csrfToken }),
        },
        credentials: 'include',
        body: JSON.stringify({}),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.access_token) {
          this.token = data.access_token;
          return true;
        }
      }
    } catch {
      // Refresh failed silently
    }
    return false;
  },

  /**
   * Low-level fetch wrapper that adds Authorization and CSRF headers.
   * Unlike request, this takes a full URL and returns the raw
   * Response without parsing or error-throwing, matching the old authFetch
   * function that was previously defined in App.jsx.
   */
  authFetch(url: string, options: RequestOptions = {}) {
    const token = this.getToken();
    const csrfToken = getCookie('_csrf');
    const method = (options.method || 'GET').toUpperCase();
    const isFormData = options.body instanceof FormData;

    const headers: Record<string, string> = {
      ...(!isFormData && { 'Content-Type': 'application/json' }),
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method) && { 'X-CSRF-Token': csrfToken }),
      ...options.headers,
    };

    return fetch(url, { ...options, headers, credentials: 'include' });
  },
} as ApiClient;
