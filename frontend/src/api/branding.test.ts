import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => {
  const api = {
    request: vi.fn(),
    authFetch: vi.fn(),
    getToken: vi.fn().mockReturnValue('test-token'),
  };
  return { api, API_BASE_URL: 'http://localhost:8000/api/v1' };
});

vi.mock('../utils', () => ({
  getCookie: vi.fn().mockReturnValue('csrf-token'),
}));

import { api } from './client';
import './branding';

describe('api/branding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getToken as any).mockReturnValue('test-token');
  });

  it('registers expected methods on api object', () => {
    expect(typeof (api as any).getBranding).toBe('function');
    expect(typeof (api as any).updateBranding).toBe('function');
    expect(typeof (api as any).uploadBrandingLogo).toBe('function');
    expect(typeof (api as any).resetBranding).toBe('function');
  });

  it('getBranding calls api.request with /branding', async () => {
    (api.request as any).mockResolvedValue({ primary_color: '#000' });
    const result = await (api as any).getBranding();
    expect(api.request).toHaveBeenCalledWith('/branding');
    expect(result.primary_color).toBe('#000');
  });

  it('updateBranding calls PUT /branding with config', async () => {
    const config = { primary_color: '#fff' };
    (api.request as any).mockResolvedValue(config);
    await (api as any).updateBranding(config);
    expect(api.request).toHaveBeenCalledWith('/branding', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  });

  it('uploadBrandingLogo posts FormData to /branding/logo via api.request', async () => {
    const mockFile = new File(['logo'], 'logo.png', { type: 'image/png' });
    (api.request as any).mockResolvedValue({ status: 'ok', logo_url: '/logo.png' });

    const result = await (api as any).uploadBrandingLogo(mockFile);
    expect(api.request).toHaveBeenCalledWith(
      '/branding/logo',
      expect.objectContaining({ method: 'POST' }),
    );
    const [, options] = (api.request as any).mock.calls[0];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get('file')).toBe(mockFile);
    expect(result.logo_url).toBe('/logo.png');
  });

  it('uploadBrandingLogo propagates errors from api.request', async () => {
    const mockFile = new File(['logo'], 'logo.png', { type: 'image/png' });
    (api.request as any).mockRejectedValue(new Error('Too large'));

    await expect((api as any).uploadBrandingLogo(mockFile)).rejects.toThrow('Too large');
  });

  it('resetBranding calls POST /branding/reset', async () => {
    (api.request as any).mockResolvedValue({ primary_color: '#default' });
    await (api as any).resetBranding();
    expect(api.request).toHaveBeenCalledWith('/branding/reset', { method: 'POST' });
  });
});
