import { api } from './client';
import type { BrandingConfig } from './types';

Object.assign(api, {
  async getBranding(): Promise<BrandingConfig> {
    return api.request('/branding');
  },

  async updateBranding(config: Partial<BrandingConfig>): Promise<BrandingConfig> {
    return api.request('/branding', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  async uploadBrandingLogo(file: File): Promise<{ status: string; logo_url: string }> {
    const formData = new FormData();
    formData.append('file', file);

    return api.request('/branding/logo', { method: 'POST', body: formData });
  },

  async resetBranding(): Promise<BrandingConfig> {
    return api.request('/branding/reset', { method: 'POST' });
  },
});
