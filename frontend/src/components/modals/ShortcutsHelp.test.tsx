import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ShortcutsHelp } from './ShortcutsHelp';

describe('ShortcutsHelp', () => {
  it('returns null when isOpen is false', () => {
    const { container } = render(
      <ShortcutsHelp isOpen={false} onClose={vi.fn()} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders when isOpen is true', () => {
    const { container } = render(<ShortcutsHelp isOpen={true} onClose={vi.fn()} />);
    expect(container.innerHTML.length).toBeGreaterThan(0);
    // Should render keyboard shortcuts
    expect(container.querySelectorAll('kbd').length).toBeGreaterThan(0);
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(<ShortcutsHelp isOpen={true} onClose={onClose} />);
    // Find the close button (typically has X or close text)
    const buttons = screen.getAllByRole('button');
    const closeBtn = buttons.find(
      (b: HTMLElement) => b.textContent?.includes('X') || b.textContent?.includes('×') || b.getAttribute('aria-label')?.includes('close')
    ) || buttons[0];
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('renders keyboard shortcut entries', () => {
    render(<ShortcutsHelp isOpen={true} onClose={vi.fn()} />);
    // Should render at least one <kbd> element
    const kbdElements = document.querySelectorAll('kbd');
    expect(kbdElements.length).toBeGreaterThan(0);
  });
});
