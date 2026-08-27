import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../../stores/brandingStore', () => ({
  useBrandingStore: (selector: any) => {
    const state = {
      branding: {
        firm_name: 'Test Firm',
        primary_color: '#1a1a2e',
        secondary_color: '#16213e',
        accent_color: '#e2b714',
        logo_url: '',
      },
      saveBranding: vi.fn(),
      uploadLogo: vi.fn(),
      resetBranding: vi.fn(),
    };
    return selector(state);
  },
}));

vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (selector: any) => {
    const state = { addToast: vi.fn() };
    return selector(state);
  },
}));

import { BrandingTab } from './BrandingTab';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    ...overrides,
  };
}

describe('BrandingTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the firm name input', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Firm Name');
  });

  it('shows color inputs', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Primary');
    expect(container.textContent).toContain('Secondary');
    expect(container.textContent).toContain('Accent');
  });

  it('shows logo upload area', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Logo');
    expect(container.textContent).toContain('Click or drag to upload');
  });

  it('shows preview section', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Preview');
  });

  it('has save and reset buttons', () => {
    const { container } = render(<BrandingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Save Branding');
    expect(container.textContent).toContain('Reset Defaults');
  });
});
