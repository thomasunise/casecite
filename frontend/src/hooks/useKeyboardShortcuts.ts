import { useEffect, useCallback } from 'react';

/**
 * Centralized keyboard shortcuts hook for the CaseCite platform.
 *
 * @param {Object} options
 * @param {Function} options.setActiveMode - Setter for the current analysis mode
 * @param {Function} options.setLeftSidebarCollapsed - Toggle left sidebar
 * @param {Function} options.setRightSidebarCollapsed - Toggle right panel
 * @param {Object}   options.inputRef - Ref to the main search/chat input
 * @param {Function} options.setShowShortcutsHelp - Show/hide the shortcuts help overlay
 * @param {boolean}  options.showShortcutsHelp - Current shortcuts help visibility
 * @param {Function} options.closeAllModals - Function to close any open modal/panel
 * @param {string[]} options.modeIds - Ordered array of mode IDs for Ctrl+1-8 switching
 */
export function useKeyboardShortcuts({
  setActiveMode,
  setLeftSidebarCollapsed,
  setRightSidebarCollapsed,
  inputRef,
  setShowShortcutsHelp,
  showShortcutsHelp,
  closeAllModals,
  modeIds = [],
}: {
  setActiveMode: (mode: string) => void;
  setLeftSidebarCollapsed: (val: boolean | ((prev: boolean) => boolean)) => void;
  setRightSidebarCollapsed: (val: boolean | ((prev: boolean) => boolean)) => void;
  inputRef: React.RefObject<HTMLElement | null>;
  setShowShortcutsHelp: (val: boolean | ((prev: boolean) => boolean)) => void;
  showShortcutsHelp: boolean;
  closeAllModals?: (() => void) | null;
  modeIds?: string[];
}) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const isMod = e.metaKey || e.ctrlKey;
    const tag = document.activeElement?.tagName?.toLowerCase();
    const isInInput = tag === 'input' || tag === 'textarea' || tag === 'select' ||
      (document.activeElement as HTMLElement)?.isContentEditable;

    // Escape - close any open modal/panel
    if (e.key === 'Escape') {
      if (showShortcutsHelp) {
        e.preventDefault();
        setShowShortcutsHelp(false);
        return;
      }
      if (closeAllModals) {
        closeAllModals();
      }
      return;
    }

    // ? - Show shortcuts help (only when not typing in an input)
    if (e.key === '?' && !isMod && !isInInput) {
      e.preventDefault();
      setShowShortcutsHelp(prev => !prev);
      return;
    }

    // All remaining shortcuts require Ctrl/Cmd
    if (!isMod) return;

    // Ctrl/Cmd + K - Focus search input
    if (e.key === 'k' || e.key === 'K') {
      e.preventDefault();
      inputRef?.current?.focus();
      return;
    }

    // Ctrl/Cmd + B - Toggle left sidebar
    if (e.key === 'b' || e.key === 'B') {
      e.preventDefault();
      setLeftSidebarCollapsed(prev => !prev);
      return;
    }

    // Ctrl/Cmd + . - Toggle right panel
    if (e.key === '.') {
      e.preventDefault();
      setRightSidebarCollapsed(prev => !prev);
      return;
    }

    // Ctrl/Cmd + P - Print current view
    if (e.key === 'p' || e.key === 'P') {
      e.preventDefault();
      window.print();
      return;
    }

    // Ctrl/Cmd + 1-8 - Switch between modes
    const num = parseInt(e.key, 10);
    if (num >= 1 && num <= 8 && num <= modeIds.length) {
      e.preventDefault();
      setActiveMode(modeIds[num - 1]);
      return;
    }
  }, [
    setActiveMode,
    setLeftSidebarCollapsed,
    setRightSidebarCollapsed,
    inputRef,
    setShowShortcutsHelp,
    showShortcutsHelp,
    closeAllModals,
    modeIds,
  ]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

/**
 * List of all available shortcuts for display in the help overlay.
 */
export const SHORTCUTS_LIST = [
  { keys: ['Ctrl', 'K'], description: 'Focus search input' },
  { keys: ['Ctrl', '1-8'], description: 'Switch analysis mode' },
  { keys: ['Ctrl', 'B'], description: 'Toggle left sidebar' },
  { keys: ['Ctrl', '.'], description: 'Toggle right panel' },
  { keys: ['Ctrl', 'P'], description: 'Print current view' },
  { keys: ['?'], description: 'Show keyboard shortcuts' },
  { keys: ['Esc'], description: 'Close modal / panel' },
];
