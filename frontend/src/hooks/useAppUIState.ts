import { useRef, useCallback, useMemo } from 'react';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';
import { useUIStore } from '../stores/uiStore';
import { ANALYSIS_MODES } from '../constants/analysisModes';
import type { Citation } from '../types';

/**
 * Manages the shared file input ref and global keyboard shortcuts.
 * All other UI state has been migrated to Zustand stores — consumers
 * import directly from useUIStore, useAuthStore, etc.
 */
export function useAppUIState({
  setSelectedCitation, setShowSignupModal, setShowLoginModal,
  setShowPickerModal,
  setActiveMode, inputRef,
}: {
  setSelectedCitation: (val: Citation | null) => void;
  setShowSignupModal: (val: boolean) => void;
  setShowLoginModal: (val: boolean) => void;
  setShowPickerModal: (val: boolean) => void;
  setActiveMode: (mode: string) => void;
  inputRef: React.RefObject<HTMLElement | null>;
}) {
  // State from store (needed for keyboard shortcuts)
  const setShowSettings = useUIStore((s) => s.setShowSettings);
  const showShortcutsHelp = useUIStore((s) => s.showShortcutsHelp);
  const setShowShortcutsHelp = useUIStore((s) => s.setShowShortcutsHelp);
  const setLeftSidebarCollapsed = useUIStore((s) => s.setLeftSidebarCollapsed);
  const setRightSidebarCollapsed = useUIStore((s) => s.setRightSidebarCollapsed);

  // React ref (can't live in Zustand)
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Close all modals (used by keyboard shortcut Escape handler)
  const closeAllModals = useCallback(() => {
    setShowSettings(false);
    setSelectedCitation(null);
    setShowSignupModal(false);
    setShowLoginModal(false);
    setShowPickerModal(false);
  }, [setShowSettings, setSelectedCitation, setShowSignupModal, setShowLoginModal, setShowPickerModal]);

  // Global keyboard shortcuts
  const modeIds = useMemo(() => ANALYSIS_MODES.map(m => m.id), []);
  useKeyboardShortcuts({
    setActiveMode,
    setLeftSidebarCollapsed,
    setRightSidebarCollapsed,
    inputRef,
    setShowShortcutsHelp,
    showShortcutsHelp,
    closeAllModals,
    modeIds,
  });

  return { fileInputRef };
}

export type AppUIState = ReturnType<typeof useAppUIState>;
