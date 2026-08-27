import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../utils', () => ({ getCookie: vi.fn(() => null) }));

import { api } from './client';

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
    for (const endpoint of ['/auth/register', '/auth/mfa/verify', '/auth/mfa/recovery', '/auth/demo/login', '/auth/azure/login']) {
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
