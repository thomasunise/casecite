import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmModal } from './ConfirmModal';

describe('ConfirmModal', () => {
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <ConfirmModal isOpen={false} onClose={vi.fn()} title="Test" message="msg" />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders title and message when open', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} title="Delete?" message="Are you sure?" />
    );
    expect(screen.getByText('Delete?')).toBeInTheDocument();
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
  });

  it('has ARIA attributes for accessibility', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} title="T" message="M" />
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-modal-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'confirm-modal-message');
  });

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(
      <ConfirmModal isOpen={true} onClose={onClose} title="T" message="M" />
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when clicking the overlay', () => {
    const onClose = vi.fn();
    const { container } = render(
      <ConfirmModal isOpen={true} onClose={onClose} title="T" message="M" />
    );
    // The overlay is the outermost div
    fireEvent.click(container.firstChild!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not close when clicking inside the modal dialog', () => {
    const onClose = vi.fn();
    render(
      <ConfirmModal isOpen={true} onClose={onClose} title="T" message="M" />
    );
    const dialog = screen.getByRole('dialog');
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('shows OK button (not Confirm) when no onConfirm prop', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} title="Info" message="msg" />
    );
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
  });

  it('shows Confirm and Cancel buttons when onConfirm is provided', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} title="T" message="M" />
    );
    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls onConfirm when Confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} onConfirm={onConfirm} title="T" message="M" />
    );
    fireEvent.click(screen.getByText('Confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('applies danger color for danger type', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} title="T" message="M" type="danger" />
    );
    const confirmBtn = screen.getByText('Confirm');
    expect(confirmBtn.style.background).toBe('rgb(231, 76, 60)');
  });

  it('applies warning color for warning type', () => {
    render(
      <ConfirmModal isOpen={true} onClose={vi.fn()} onConfirm={vi.fn()} title="T" message="M" type="warning" />
    );
    const confirmBtn = screen.getByText('Confirm');
    expect(confirmBtn.style.background).toBe('rgb(245, 166, 35)');
  });
});
