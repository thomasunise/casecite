import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../api', () => ({
  api: { getDocumentTree: vi.fn().mockResolvedValue({ tree: [], total_documents: 0 }) },
}));

vi.mock('../../utils/logger', () => ({
  default: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

vi.mock('../../utils', () => ({
  formatFileSize: (size: number) => `${(size / 1024).toFixed(0)} KB`,
}));

import { ContractFilePicker } from './ContractFilePicker';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    onSelect: vi.fn(),
    loading: false,
    ...overrides,
  };
}

describe('ContractFilePicker', () => {
  it('renders without crashing when open', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('returns null when not open', () => {
    const { container } = render(<ContractFilePicker {...defaultProps({ isOpen: false })} />);
    expect(container.innerHTML).toBe('');
  });

  it('shows the header', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    expect(container.textContent).toContain('Browse Documents');
  });

  it('shows subtitle', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    expect(container.textContent).toContain('Pick one document to analyze');
  });

  it('shows search input', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    const searchInput = container.querySelector('input[type="text"]');
    expect(searchInput).toBeTruthy();
  });

  it('shows cancel and load buttons in footer', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    expect(container.textContent).toContain('Cancel');
    expect(container.textContent).toContain('Load Document');
  });

  it('shows documents available count in footer', () => {
    const { container } = render(<ContractFilePicker {...defaultProps()} />);
    expect(container.textContent).toContain('0 documents available');
  });
});
