import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../api', () => ({
  api: { getDocumentTree: vi.fn().mockResolvedValue({ tree: [], total_documents: 0 }) },
}));

vi.mock('../../utils', () => ({
  formatFileSize: (n: number) => `${n} B`,
}));

vi.mock('../../utils/logger', () => ({
  default: { error: vi.fn() },
}));

import { DocumentSelector } from './DocumentSelector';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    onSelect: vi.fn(),
    currentFilter: null,
    ...overrides,
  };
}

describe('DocumentSelector', () => {
  it('renders without crashing when open', () => {
    const { container } = render(<DocumentSelector {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('returns null when not open', () => {
    const { container } = render(<DocumentSelector {...defaultProps({ isOpen: false })} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders header title', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByText('Select Documents')).toBeTruthy();
  });

  it('renders search input placeholder', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByPlaceholderText('Search folders and files...')).toBeTruthy();
  });

  it('renders All Documents button', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByText('All Documents')).toBeTruthy();
  });

  it('renders Clear Selection button', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByText('Clear Selection')).toBeTruthy();
  });

  it('renders Cancel and Apply Filter buttons', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByText('Cancel')).toBeTruthy();
    expect(screen.getByText('Apply Filter')).toBeTruthy();
  });

  it('shows loading state initially', () => {
    render(<DocumentSelector {...defaultProps()} />);
    expect(screen.getByText('Loading document tree...')).toBeTruthy();
  });
});
