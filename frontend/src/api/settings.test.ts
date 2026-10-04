import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => {
  const api = {
    request: vi.fn(),
    authFetch: vi.fn(),
  };
  return { api, API_BASE_URL: 'http://localhost:8000/api/v1' };
});

import { api } from './client';
import './settings';

describe('api/settings', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('registers expected methods on api object', () => {
    expect(typeof (api as any).getSettings).toBe('function');
    expect(typeof (api as any).updateSettings).toBe('function');
  });

  it('getSettings calls GET /settings/rag', async () => {
    (api.request as any).mockResolvedValue({ model: 'gpt-5.5', temperature: 0.7 });
    const result = await (api as any).getSettings();
    expect(api.request).toHaveBeenCalledWith('/settings/rag');
    expect(result.model).toBe('gpt-5.5');
  });

  it('updateSettings calls PUT /settings/rag with settings', async () => {
    const settings = { model: 'gpt-5.5', temperature: 0.5 };
    (api.request as any).mockResolvedValue(settings);
    const result = await (api as any).updateSettings(settings);
    expect(api.request).toHaveBeenCalledWith('/settings/rag', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
    expect(result.temperature).toBe(0.5);
  });
});
