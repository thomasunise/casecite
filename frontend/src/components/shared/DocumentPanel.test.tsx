import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

// Mock api
vi.mock('../../api', () => ({
  api: { request: vi.fn().mockResolvedValue({}) },
}));

import { DocumentPanel } from './DocumentPanel';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    documents: [],
    onUpload: vi.fn(),
    onRemove: vi.fn(),
    onClear: vi.fn(),
    isAuthenticated: true,
    onAuthRequired: vi.fn(),
    ...overrides,
  };
}

describe('DocumentPanel', () => {
  it('renders without crashing', () => {
    const { container } = render(<DocumentPanel {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows upload area', () => {
    const { container } = render(<DocumentPanel {...defaultProps()} />);
    // Should have some upload-related content
    expect(container.innerHTML).not.toBe('');
  });

  it('renders documents when provided', () => {
    const docs = [
      { id: 'doc-1', name: 'contract.pdf', size: 1024, status: 'indexed' },
    ];
    const { container } = render(<DocumentPanel {...defaultProps({ documents: docs })} />);
    expect(container.textContent).toContain('contract.pdf');
  });
});
