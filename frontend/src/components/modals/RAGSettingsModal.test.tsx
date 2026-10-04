import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { useAuthStore } from '../../stores/authStore';
import { RAGSettingsModal } from './RAGSettingsModal';

// The modal loads server-side key status when it opens.
vi.mock('../../api', () => ({
  api: {
    getKeyStatus: vi.fn().mockResolvedValue({
      openai_configured: false,
      anthropic_configured: false,
      google_configured: false,
      voyage_configured: false,
      cohere_configured: false,
    }),
    getMaskedKeys: vi.fn().mockResolvedValue({}),
  },
}));

type RAGSettingsModalProps = React.ComponentProps<typeof RAGSettingsModal>;

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    settings: {
      vectorDb: 'chroma',
      topK: 10,
      embeddingModel: 'text-embedding-3-small',
    },
    onSave: vi.fn(),
    ...overrides,
  } as unknown as RAGSettingsModalProps;
}

describe('RAGSettingsModal', () => {
  beforeEach(() => {
    // Settings is gated behind login as a whole.
    useAuthStore.setState({ isAuthenticated: true });
  });

  it('renders when isOpen is true', () => {
    const { container } = render(<RAGSettingsModal {...defaultProps()} />);
    expect(container.innerHTML).not.toBe('');
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(<RAGSettingsModal {...defaultProps({ isOpen: false })} />);
    expect(container.innerHTML).toBe('');
  });

  it('does not render when not authenticated', () => {
    useAuthStore.setState({ isAuthenticated: false });
    const { container } = render(<RAGSettingsModal {...defaultProps()} />);
    expect(container.innerHTML).toBe('');
  });

  it('contains form inputs', () => {
    const { container } = render(<RAGSettingsModal {...defaultProps()} />);
    const inputs = container.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('has close/save buttons', () => {
    const { container } = render(<RAGSettingsModal {...defaultProps()} />);
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(0);
  });
});
