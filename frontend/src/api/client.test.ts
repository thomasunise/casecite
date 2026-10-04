import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../utils', () => ({ getCookie: vi.fn(() => null) }));

import { api, formatErrorDetail } from './client';

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe('api/client 401 handling', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    api.token = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('surfaces the server message for a wrong password without trying to refresh', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: 'Invalid email or password' }));

    await expect(
      api.request('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'a', password: 'b' }) }),
    ).rejects.toThrow('Invalid email or password');

    // One call: the login itself. No /auth/refresh, no retry.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/auth/login');
  });

  it('treats the other credential endpoints the same way', async () => {
    for (const endpoint of ['/auth/register', '/auth/mfa/verify']) {
      fetchMock.mockReset();
      fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: `nope: ${endpoint}` }));
      await expect(api.request(endpoint, { method: 'POST' })).rejects.toThrow(`nope: ${endpoint}`);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });

  it('falls back to a generic message when a credential 401 has no detail', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 401, json: async () => { throw new Error('no body'); } });
    await expect(api.request('/auth/login', { method: 'POST' })).rejects.toThrow('Invalid credentials');
  });

  it('still refreshes and retries once for a 401 on a normal endpoint', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'Token expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'fresh' }))
      .mockResolvedValueOnce(jsonResponse(200, { documents: [] }));

    const result = await api.request('/documents');

    expect(result).toEqual({ documents: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain('/auth/refresh');
    expect(api.token).toBe('fresh');
  });
});

describe('api/client error messages', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    api.token = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('formats a FastAPI 422 validation array instead of "[object Object]"', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(422, {
      detail: [
        { loc: ['body', 'vector_db'], msg: "String should match pattern '^(chroma|pinecone)$'", type: 'string_pattern_mismatch' },
        { loc: ['body', 'chunk_size'], msg: 'Input should be less than or equal to 2000', type: 'less_than_equal' },
      ],
    }));

    await expect(api.request('/settings/rag', { method: 'PUT', body: '{}' })).rejects.toThrow(
      "vector_db: String should match pattern '^(chroma|pinecone)$'; chunk_size: Input should be less than or equal to 2000",
    );
  });

  it('formatErrorDetail handles strings, arrays, objects and junk', () => {
    expect(formatErrorDetail('Nope', 'fallback')).toBe('Nope');
    expect(formatErrorDetail([{ loc: ['query', 'limit'], msg: 'too big' }], 'fallback')).toBe('limit: too big');
    expect(formatErrorDetail({ message: 'From object' }, 'fallback')).toBe('From object');
    expect(formatErrorDetail(undefined, 'fallback')).toBe('fallback');
    expect(formatErrorDetail([], 'fallback')).toBe('fallback');
    expect(formatErrorDetail([{}], 'fallback')).toBe('fallback');
  });

  it('reports a timeout as a timeout', async () => {
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    await expect(api.request('/documents', { timeout: 5 })).rejects.toThrow('The request timed out');
  });

  it('lets the caller cancel a request through its own signal', async () => {
    const controller = new AbortController();
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const pending = api.request('/chat', { method: 'POST', signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('api.authFetch', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    api.token = 'stale';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('refreshes once on 401 and retries with the fresh token, not the caller\'s stale header', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'Token expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'fresh' }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    const resp = await api.authFetch('http://localhost:8000/api/v1/tools/cases/1', {
      headers: { Authorization: 'Bearer stale' },
    });

    expect(resp.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain('/auth/refresh');
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer fresh');
  });

  it('returns the 401 response (and drops the token) when the session cannot be refreshed', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'Token expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'No refresh token' }));

    const resp = await api.authFetch('http://localhost:8000/api/v1/judge-intel/search?q=x');

    expect(resp.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(api.token).toBeNull();
  });

  it('honours the timeout option', async () => {
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    await expect(api.authFetch('http://localhost:8000/api/v1/x', { timeout: 5 })).rejects.toThrow('The request timed out');
  });
});

describe('api/client account gates', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    api.token = 't';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('a 403 with code password_change_required flags the signed-in user', async () => {
    const { useAuthStore } = await import('../stores/authStore');
    useAuthStore.setState({ user: { id: 'u1', email: 'a@b.c', roles: ['attorney'] }, isAuthenticated: true });
    fetchMock.mockResolvedValueOnce(jsonResponse(403, {
      detail: 'Change your temporary password to continue.', code: 'password_change_required',
    }));

    await expect(api.request('/documents')).rejects.toThrow('Change your temporary password to continue.');

    await vi.waitFor(() => expect(useAuthStore.getState().user?.must_change_password).toBe(true));
  });

  it('a 403 with code mfa_enrollment_required opens Settings on the Security tab', async () => {
    const { useAuthStore } = await import('../stores/authStore');
    const { useUIStore } = await import('../stores/uiStore');
    useUIStore.setState(useUIStore.getInitialState(), true);
    useAuthStore.setState({ user: { id: 'u1', email: 'a@b.c', roles: ['attorney'] }, isAuthenticated: true });
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { detail: 'Set up MFA.', code: 'mfa_enrollment_required' }));

    await expect(api.request('/documents')).rejects.toThrow('Set up MFA.');

    await vi.waitFor(() => expect(useUIStore.getState().settingsTab).toBe('security'));
    expect(useUIStore.getState().showSettings).toBe(true);
    expect(useAuthStore.getState().user?.mfa_enrollment_required).toBe(true);
  });

  it('an ordinary 403 changes nothing', async () => {
    const { useAuthStore } = await import('../stores/authStore');
    useAuthStore.setState({ user: { id: 'u1', email: 'a@b.c', roles: ['viewer'] }, isAuthenticated: true });
    fetchMock.mockResolvedValueOnce(jsonResponse(403, { detail: 'Insufficient permissions' }));

    await expect(api.request('/admin/users')).rejects.toThrow('Insufficient permissions');
    await new Promise((r) => setTimeout(r, 20));

    expect(useAuthStore.getState().user?.must_change_password).toBeUndefined();
  });
});
