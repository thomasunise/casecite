import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => {
  const api = {
    request: vi.fn(),
    authFetch: vi.fn(),
  };
  return { api, API_BASE_URL: 'http://localhost:8000/api/v1' };
});

import { api } from './client';
import './connectors';

describe('api/connectors', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('registers expected methods on api object', () => {
    expect(typeof (api as any).getConnectors).toBe('function');
    expect(typeof (api as any).connectConnector).toBe('function');
    expect(typeof (api as any).disconnectConnector).toBe('function');
    expect(typeof (api as any).syncConnector).toBe('function');
    expect(typeof (api as any).getConnectorStatus).toBe('function');
  });

  it('getConnectors calls GET /connectors', async () => {
    (api.request as any).mockResolvedValue([{ id: 'clio', connected: true }]);
    const result = await (api as any).getConnectors();
    expect(api.request).toHaveBeenCalledWith('/connectors');
    expect(result).toHaveLength(1);
  });

  it('connectConnector calls GET /connectors/:id/auth', async () => {
    (api.request as any).mockResolvedValue({ auth_url: 'https://auth.example.com' });
    const result = await (api as any).connectConnector('clio');
    expect(api.request).toHaveBeenCalledWith('/connectors/clio/auth');
    expect(result.auth_url).toBe('https://auth.example.com');
  });

  it('disconnectConnector calls POST /connectors/:id/disconnect', async () => {
    (api.request as any).mockResolvedValue({ message: 'disconnected' });
    await (api as any).disconnectConnector('google');
    expect(api.request).toHaveBeenCalledWith('/connectors/google/disconnect', { method: 'POST' });
  });

  it('syncConnector calls POST /connectors/:id/sync with options', async () => {
    (api.request as any).mockResolvedValue({ message: 'syncing' });
    await (api as any).syncConnector('dropbox', { full: true });
    expect(api.request).toHaveBeenCalledWith('/connectors/dropbox/sync', {
      method: 'POST',
      body: JSON.stringify({ full: true }),
    });
  });

  it('syncConnector defaults options to empty object', async () => {
    (api.request as any).mockResolvedValue({ message: 'syncing' });
    await (api as any).syncConnector('dropbox');
    expect(api.request).toHaveBeenCalledWith('/connectors/dropbox/sync', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  });

  it('getConnectorStatus calls GET /connectors/:id/status', async () => {
    (api.request as any).mockResolvedValue({ id: 'clio', status: 'active' });
    const result = await (api as any).getConnectorStatus('clio');
    expect(api.request).toHaveBeenCalledWith('/connectors/clio/status');
    expect(result.status).toBe('active');
  });
});
