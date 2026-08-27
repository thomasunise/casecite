import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModalShell } from './ModalShell';

function Dialog({ onClose, isOpen = true, title = 'Title' }: { onClose: () => void; isOpen?: boolean; title?: string }) {
  return (
    <ModalShell isOpen={isOpen} onClose={onClose} labelledBy={`${title}-id`} overlayClassName="ov" className="panel">
      <h2 id={`${title}-id`}>{title}</h2>
      <button>First</button>
      <input aria-label="Middle" />
      <button>Last</button>
    </ModalShell>
  );
}

describe('ModalShell', () => {
  it('renders a labelled modal dialog', () => {
    render(<Dialog onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog', { name: 'Title' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('renders nothing when closed', () => {
    const { container } = render(<Dialog onClose={vi.fn()} isOpen={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('moves focus into the dialog on open and restores it on close', () => {
    const { rerender } = render(
      <>
        <button>Trigger</button>
        <Dialog onClose={vi.fn()} isOpen={false} />
      </>,
    );
    const trigger = screen.getByText('Trigger');
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    rerender(
      <>
        <button>Trigger</button>
        <Dialog onClose={vi.fn()} isOpen={true} />
      </>,
    );
    expect(document.activeElement).toBe(screen.getByText('First'));

    rerender(
      <>
        <button>Trigger</button>
        <Dialog onClose={vi.fn()} isOpen={false} />
      </>,
    );
    expect(document.activeElement).toBe(trigger);
  });

  it('closes on Escape exactly once and keeps the key from window listeners', () => {
    const onClose = vi.fn();
    const windowListener = vi.fn();
    window.addEventListener('keydown', windowListener);
    try {
      render(<Dialog onClose={onClose} />);
      fireEvent.keyDown(document.activeElement || document, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(windowListener).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener('keydown', windowListener);
    }
  });

  it('cycles focus with Tab and Shift+Tab', () => {
    render(<Dialog onClose={vi.fn()} />);
    const first = screen.getByText('First');
    const last = screen.getByText('Last');

    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);

    // Keyboard events go to the focused element; the trap walks from wherever
    // focus actually is, so move it back to First before stepping forward.
    first.focus();
    fireEvent.keyDown(first, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByLabelText('Middle'));
  });

  it('closes on backdrop click but not on clicks inside the panel', () => {
    const onClose = vi.fn();
    const { container } = render(<Dialog onClose={onClose} />);
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(container.firstChild!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ignores a drag that starts inside the panel and ends on the backdrop', () => {
    const onClose = vi.fn();
    const { container } = render(<Dialog onClose={onClose} />);
    fireEvent.mouseDown(screen.getByRole('dialog'));
    fireEvent.click(container.firstChild!);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('lets only the topmost of stacked dialogs handle Escape', () => {
    const closeOuter = vi.fn();
    const closeInner = vi.fn();
    render(
      <>
        <Dialog onClose={closeOuter} title="Outer" />
        <Dialog onClose={closeInner} title="Inner" />
      </>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(closeInner).toHaveBeenCalledTimes(1);
    expect(closeOuter).not.toHaveBeenCalled();
  });
});
