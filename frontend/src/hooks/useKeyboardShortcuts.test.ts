import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useKeyboardShortcuts, SHORTCUTS_LIST } from './useKeyboardShortcuts';

function fireKey(key: string, opts: Partial<KeyboardEventInit> = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, ...opts });
  window.dispatchEvent(event);
}

function createOptions(overrides: Record<string, any> = {}) {
  return {
    setActiveMode: vi.fn(),
    setLeftSidebarCollapsed: vi.fn(),
    leftSidebarCollapsed: false,
    setRightSidebarCollapsed: vi.fn(),
    rightSidebarCollapsed: false,
    inputRef: { current: document.createElement('input') },
    setShowShortcutsHelp: vi.fn(),
    showShortcutsHelp: false,
    closeAllModals: vi.fn(),
    modeIds: ['research', 'drafting', 'templates', 'clauses'],
    ...overrides,
  };
}

describe('useKeyboardShortcuts', () => {
  it('Escape calls closeAllModals', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('Escape');
    expect(opts.closeAllModals).toHaveBeenCalled();
  });

  it('Escape closes shortcuts help when open', () => {
    const opts = createOptions({ showShortcutsHelp: true });
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('Escape');
    expect(opts.setShowShortcutsHelp).toHaveBeenCalledWith(false);
  });

  it('? toggles shortcuts help', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('?');
    expect(opts.setShowShortcutsHelp).toHaveBeenCalled();
  });

  it('Ctrl+K focuses input', () => {
    const opts = createOptions();
    const focusSpy = vi.spyOn(opts.inputRef.current!, 'focus');
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('k', { ctrlKey: true });
    expect(focusSpy).toHaveBeenCalled();
  });

  it('Ctrl+B toggles left sidebar', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('b', { ctrlKey: true });
    expect(opts.setLeftSidebarCollapsed).toHaveBeenCalled();
  });

  it('Ctrl+. toggles right panel', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('.', { ctrlKey: true });
    expect(opts.setRightSidebarCollapsed).toHaveBeenCalled();
  });

  it('Ctrl+1 switches to first mode', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('1', { ctrlKey: true });
    expect(opts.setActiveMode).toHaveBeenCalledWith('research');
  });

  it('Ctrl+4 switches to fourth mode', () => {
    const opts = createOptions();
    renderHook(() => useKeyboardShortcuts(opts));
    fireKey('4', { ctrlKey: true });
    expect(opts.setActiveMode).toHaveBeenCalledWith('clauses');
  });

  it('removes listener on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const opts = createOptions();
    const { unmount } = renderHook(() => useKeyboardShortcuts(opts));
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function));
    removeSpy.mockRestore();
  });

  it('SHORTCUTS_LIST has expected entries', () => {
    expect(SHORTCUTS_LIST.length).toBeGreaterThanOrEqual(7);
    const descriptions = SHORTCUTS_LIST.map(s => s.description);
    expect(descriptions).toContain('Focus search input');
    expect(descriptions).toContain('Close modal / panel');
  });
});
