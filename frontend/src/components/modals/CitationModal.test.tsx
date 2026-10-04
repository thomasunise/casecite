import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { CitationModal } from './CitationModal';

type CitationModalProps = React.ComponentProps<typeof CitationModal>;

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    isOpen: true,
    onClose: vi.fn(),
    citation: {
      id: 'cit-1',
      text: 'Smith v. Jones, 123 F.3d 456 (9th Cir. 2023)',
      status: 'pending',
      notes: '',
    },
    onUpdateStatus: vi.fn(),
    ...overrides,
  } as unknown as CitationModalProps;
}

describe('CitationModal', () => {
  it('renders when isOpen and citation provided', () => {
    const { container } = render(<CitationModal {...defaultProps()} />);
    expect(container.innerHTML).not.toBe('');
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(<CitationModal {...defaultProps({ isOpen: false })} />);
    expect(container.innerHTML).toBe('');
  });

  it('does not render when citation is null', () => {
    const { container } = render(<CitationModal {...defaultProps({ citation: null })} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders interactive buttons', () => {
    const { container } = render(<CitationModal {...defaultProps()} />);
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(0);
  });
});
