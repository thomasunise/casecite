import { create } from 'zustand';
import { api } from '../api';
import type { BrandingConfig } from '../api/types';
import logger from '../utils/logger';

// ==================== Color Utilities ====================

function hexToHSL(hex: string): { h: number; s: number; l: number } {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;

  if (max === min) return { h: 0, s: 0, l };

  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;

  return { h, s, l };
}

function hslToHex(h: number, s: number, l: number): string {
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };

  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  const toHex = (v: number) => {
    const hex = Math.round(v * 255).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  };
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function lighten(hex: string, amount = 0.12): string {
  const { h, s, l } = hexToHSL(hex);
  return hslToHex(h, s, Math.min(1, l + amount));
}

function darken(hex: string, amount = 0.08): string {
  const { h, s, l } = hexToHSL(hex);
  return hslToHex(h, s, Math.max(0, l - amount));
}

function tint(hex: string, lightness: number): string {
  const { h, s } = hexToHSL(hex);
  return hslToHex(h, s, lightness);
}

/* Darken by `drop` but never end lighter than `cap` — the -600/-700 shades are
   used as text/borders on white surfaces, so a near-white primary (monochrome
   palettes) must still yield genuinely dark foreground shades. */
function darkTone(hex: string, drop: number, cap: number): string {
  const { h, s, l } = hexToHSL(hex);
  return hslToHex(h, s, Math.max(0, Math.min(l - drop, cap)));
}

/* WCAG relative luminance; > 0.179 means dark text wins the contrast ratio
   against this background, otherwise white text does. */
function relativeLuminance(hex: string): number {
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function isLight(hex: string): boolean {
  return relativeLuminance(hex) > 0.179;
}

const ON_DARK = { r: 255, g: 255, b: 255 };
const ON_LIGHT = { r: 10, g: 10, b: 10 };

function onColor(bg: string, alpha = 1): string {
  const c = isLight(bg) ? ON_LIGHT : ON_DARK;
  return alpha >= 1 ? `rgb(${c.r}, ${c.g}, ${c.b})` : `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha})`;
}

// ==================== Defaults ====================

const DEFAULT_BRANDING: BrandingConfig = {
  firm_name: 'CaseCite',
  logo_url: null,
  primary_color: '#E5E5E5',
  secondary_color: '#0A0A0A',
  accent_color: '#737373',
  favicon_url: null,
  custom_css: null,
  updated_at: null,
};

// ==================== Store ====================

interface BrandingState {
  branding: BrandingConfig;
  brandingLoading: boolean;
  loadBranding: () => Promise<void>;
  saveBranding: (config: Partial<BrandingConfig>) => Promise<void>;
  uploadLogo: (file: File) => Promise<string | null>;
  resetBranding: () => Promise<void>;
  applyBrandingColors: (config?: BrandingConfig) => void;
}

export const useBrandingStore = create<BrandingState>((set, get) => ({
  branding: DEFAULT_BRANDING,
  brandingLoading: false,

  loadBranding: async () => {
    set({ brandingLoading: true });
    try {
      const config = await api.getBranding();
      set({ branding: config });
      get().applyBrandingColors(config);
    } catch (e) {
      logger.debug('Could not load branding, using defaults:', e instanceof Error ? e.message : String(e));
    }
    set({ brandingLoading: false });
  },

  saveBranding: async (config) => {
    try {
      const updated = await api.updateBranding(config);
      set({ branding: updated });
      get().applyBrandingColors(updated);
    } catch (e) {
      logger.error('Failed to save branding:', e);
      throw e;
    }
  },

  uploadLogo: async (file) => {
    try {
      const result = await api.uploadBrandingLogo(file);
      const { branding } = get();
      const updated = { ...branding, logo_url: result.logo_url };
      set({ branding: updated });
      return result.logo_url;
    } catch (e) {
      logger.error('Failed to upload logo:', e);
      throw e;
    }
  },

  resetBranding: async () => {
    try {
      const config = await api.resetBranding();
      set({ branding: config });
      get().applyBrandingColors(config);
    } catch (e) {
      logger.error('Failed to reset branding:', e);
      throw e;
    }
  },

  applyBrandingColors: (config) => {
    const b = config || get().branding;
    const root = document.documentElement.style;

    // Primary color shades (gold)
    root.setProperty('--gold-500', b.primary_color);
    root.setProperty('--gold-600', darkTone(b.primary_color, 0.08, 0.45));
    root.setProperty('--gold-700', darkTone(b.primary_color, 0.16, 0.35));
    root.setProperty('--gold-400', lighten(b.primary_color));
    root.setProperty('--gold-300', lighten(b.primary_color, 0.2));
    root.setProperty('--gold-50', tint(b.primary_color, 0.96));

    // Secondary color (navy)
    root.setProperty('--navy-900', b.secondary_color);
    root.setProperty('--navy-800', lighten(b.secondary_color, 0.04));
    root.setProperty('--navy-700', lighten(b.secondary_color, 0.08));
    root.setProperty('--navy-600', lighten(b.secondary_color, 0.12));

    // Accent color shades
    root.setProperty('--accent-500', b.accent_color);
    root.setProperty('--accent-600', darken(b.accent_color));
    root.setProperty('--accent-400', lighten(b.accent_color, 0.12));

    // On-colors: readable text/icon colors for anything sitting on a brand color.
    // Recomputed from luminance so light brand picks flip their text dark.
    root.setProperty('--on-primary', onColor(b.primary_color));
    root.setProperty('--on-primary-muted', onColor(b.primary_color, 0.7));
    root.setProperty('--on-secondary', onColor(b.secondary_color));
    root.setProperty('--on-secondary-strong', onColor(b.secondary_color, 0.87));
    root.setProperty('--on-secondary-muted', onColor(b.secondary_color, 0.62));
    root.setProperty('--on-secondary-faint', onColor(b.secondary_color, 0.4));
    root.setProperty('--on-secondary-fill', onColor(b.secondary_color, 0.09));
    root.setProperty('--on-secondary-fill-subtle', onColor(b.secondary_color, 0.05));
    root.setProperty('--on-secondary-border', onColor(b.secondary_color, 0.1));
    root.setProperty('--on-secondary-border-strong', onColor(b.secondary_color, 0.18));
    root.setProperty('--on-accent', onColor(b.accent_color));

    // Favicon
    if (b.favicon_url) {
      const link: HTMLLinkElement =
        document.querySelector("link[rel*='icon']") || document.createElement('link');
      link.rel = 'icon';
      link.href = b.favicon_url;
      if (!link.parentNode) document.head.appendChild(link);
    }
  },
}));
