import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  api: {
    getBranding: vi.fn(),
    updateBranding: vi.fn(),
    uploadBrandingLogo: vi.fn(),
    resetBranding: vi.fn(),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

vi.mock('../utils/logger', () => ({ default: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { useBrandingStore } from './brandingStore';
import { api } from '../api';

const DEFAULT_BRANDING = {
  firm_name: 'CaseCite',
  logo_url: null,
  primary_color: '#E5E5E5',
  secondary_color: '#0A0A0A',
  accent_color: '#737373',
  favicon_url: null,
  custom_css: null,
  updated_at: null,
};

describe('brandingStore', () => {
  beforeEach(() => {
    useBrandingStore.setState(useBrandingStore.getInitialState(), true);
    vi.clearAllMocks();
  });

  // ==================== Initial State ====================

  it('has correct initial state', () => {
    const state = useBrandingStore.getState();
    expect(state.branding).toEqual(DEFAULT_BRANDING);
    expect(state.brandingLoading).toBe(false);
  });

  // ==================== loadBranding ====================

  it('loadBranding fetches and applies branding', async () => {
    const mockConfig = { ...DEFAULT_BRANDING, firm_name: 'Test Firm', primary_color: '#FF0000' };
    (api.getBranding as ReturnType<typeof vi.fn>).mockResolvedValue(mockConfig);

    await useBrandingStore.getState().loadBranding();

    expect(useBrandingStore.getState().branding).toEqual(mockConfig);
    expect(useBrandingStore.getState().brandingLoading).toBe(false);
  });

  it('loadBranding sets brandingLoading during fetch', async () => {
    let resolvePromise: (value: unknown) => void;
    (api.getBranding as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((res) => { resolvePromise = res; })
    );

    const promise = useBrandingStore.getState().loadBranding();
    expect(useBrandingStore.getState().brandingLoading).toBe(true);

    resolvePromise!(DEFAULT_BRANDING);
    await promise;
    expect(useBrandingStore.getState().brandingLoading).toBe(false);
  });

  it('loadBranding uses defaults on error', async () => {
    (api.getBranding as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

    await useBrandingStore.getState().loadBranding();

    expect(useBrandingStore.getState().branding).toEqual(DEFAULT_BRANDING);
    expect(useBrandingStore.getState().brandingLoading).toBe(false);
  });

  // ==================== saveBranding ====================

  it('saveBranding saves config and applies colors', async () => {
    const updated = { ...DEFAULT_BRANDING, firm_name: 'Updated Firm' };
    (api.updateBranding as ReturnType<typeof vi.fn>).mockResolvedValue(updated);

    await useBrandingStore.getState().saveBranding({ firm_name: 'Updated Firm' });

    expect(useBrandingStore.getState().branding).toEqual(updated);
    expect(api.updateBranding).toHaveBeenCalledWith({ firm_name: 'Updated Firm' });
  });

  it('saveBranding throws on error', async () => {
    (api.updateBranding as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Save failed'));

    await expect(useBrandingStore.getState().saveBranding({ firm_name: 'X' })).rejects.toThrow('Save failed');
  });

  // ==================== uploadLogo ====================

  it('uploadLogo uploads file and updates branding logo_url', async () => {
    (api.uploadBrandingLogo as ReturnType<typeof vi.fn>).mockResolvedValue({ logo_url: '/logos/new.png' });

    const file = new File(['test'], 'logo.png', { type: 'image/png' });
    const result = await useBrandingStore.getState().uploadLogo(file);

    expect(result).toBe('/logos/new.png');
    expect(useBrandingStore.getState().branding.logo_url).toBe('/logos/new.png');
  });

  it('uploadLogo throws on error', async () => {
    (api.uploadBrandingLogo as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Upload failed'));

    const file = new File(['test'], 'logo.png', { type: 'image/png' });
    await expect(useBrandingStore.getState().uploadLogo(file)).rejects.toThrow('Upload failed');
  });

  // ==================== resetBranding ====================

  it('resetBranding resets to default config', async () => {
    useBrandingStore.setState({ branding: { ...DEFAULT_BRANDING, firm_name: 'Custom' } });
    (api.resetBranding as ReturnType<typeof vi.fn>).mockResolvedValue(DEFAULT_BRANDING);

    await useBrandingStore.getState().resetBranding();

    expect(useBrandingStore.getState().branding).toEqual(DEFAULT_BRANDING);
  });

  it('resetBranding throws on error', async () => {
    (api.resetBranding as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Reset failed'));

    await expect(useBrandingStore.getState().resetBranding()).rejects.toThrow('Reset failed');
  });

  // ==================== applyBrandingColors ====================

  it('applyBrandingColors sets CSS custom properties on document root', () => {
    useBrandingStore.getState().applyBrandingColors();

    const root = document.documentElement.style;
    expect(root.getPropertyValue('--gold-500')).toBe('#E5E5E5');
    expect(root.getPropertyValue('--navy-900')).toBe('#0A0A0A');
  });

  it('applyBrandingColors accepts an explicit config', () => {
    const custom = { ...DEFAULT_BRANDING, primary_color: '#FF0000', secondary_color: '#0000FF' };
    useBrandingStore.getState().applyBrandingColors(custom);

    const root = document.documentElement.style;
    expect(root.getPropertyValue('--gold-500')).toBe('#FF0000');
    expect(root.getPropertyValue('--navy-900')).toBe('#0000FF');
  });

  it('applyBrandingColors sets favicon when favicon_url present', () => {
    const custom = { ...DEFAULT_BRANDING, favicon_url: '/favicon-custom.ico' };
    useBrandingStore.getState().applyBrandingColors(custom);

    const link = document.querySelector("link[rel*='icon']") as HTMLLinkElement;
    expect(link).toBeTruthy();
    expect(link.href).toContain('/favicon-custom.ico');
  });
});
