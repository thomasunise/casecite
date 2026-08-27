import { create } from 'zustand';
import { generateId } from '../utils';

// ==================== Toast State ====================
export interface Toast {
  id: string;
  message: string;
  type: string;
}

// ==================== Confirm Modal State ====================
export interface ConfirmModalState {
  open: boolean;
  title: string;
  message: string;
  type: string;
  confirmText: string;
  cancelText: string;
  onConfirm: (() => void) | null;
  onCancel: (() => void) | null;
}

const INITIAL_CONFIRM: ConfirmModalState = {
  open: false, title: '', message: '', type: 'info',
  confirmText: 'Confirm', cancelText: 'Cancel',
  onConfirm: null, onCancel: null,
};

// ==================== Theme ====================
export type AppTheme = 'default' | 'light';

const THEME_STORAGE_KEY = 'casecite-theme';

function applyThemeAttribute(theme: AppTheme) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

// ==================== UI Store ====================
export interface UIState {
  // Theme (per-device preference, persisted in localStorage)
  theme: AppTheme;
  initTheme: () => void;
  setTheme: (theme: AppTheme) => void;

  // Toast
  toasts: Toast[];
  addToast: (message: string, type?: string) => void;

  // Confirm modal
  confirmModal: ConfirmModalState;
  showConfirm: (opts: {
    title: string; message: string; type?: string;
    confirmText?: string; cancelText?: string;
    onConfirm?: (() => void) | null; onCancel?: (() => void) | null;
  }) => void;
  closeConfirm: () => void;
  handleConfirm: () => void;

  // UI visibility
  showSettings: boolean;
  setShowSettings: (val: boolean) => void;
  showShortcutsHelp: boolean;
  setShowShortcutsHelp: (val: boolean | ((prev: boolean) => boolean)) => void;
  rightPanelTab: string;
  setRightPanelTab: (val: string) => void;
  leftSidebarCollapsed: boolean;
  setLeftSidebarCollapsed: (val: boolean | ((prev: boolean) => boolean)) => void;
  rightSidebarCollapsed: boolean;
  setRightSidebarCollapsed: (val: boolean | ((prev: boolean) => boolean)) => void;
  // Responsive drawers — only take effect under the CSS breakpoints in
  // styles/responsive.css, where the sidebars become slide-over panels.
  leftSidebarOpen: boolean;
  setLeftSidebarOpen: (val: boolean) => void;
  rightPanelOpen: boolean;
  setRightPanelOpen: (val: boolean) => void;
  // Preview modal
  previewModal: { show: boolean; title: string; content: string };
  setPreviewModal: (val: { show: boolean; title: string; content: string }) => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  // Theme state
  theme: 'default',
  initTheme: () => {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    const theme: AppTheme = saved === 'light' ? 'light' : 'default';
    applyThemeAttribute(theme);
    set({ theme });
  },
  setTheme: (theme) => {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    applyThemeAttribute(theme);
    set({ theme });
  },

  // Toast state
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = generateId();
    set((state) => ({ toasts: [...state.toasts, { id, message, type }] }));
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter(t => t.id !== id) }));
    }, 4000);
  },

  // Confirm modal state
  confirmModal: INITIAL_CONFIRM,
  showConfirm: ({ title, message, type = 'danger', confirmText = 'Confirm', cancelText = 'Cancel', onConfirm, onCancel }) => {
    set({
      confirmModal: {
        open: true, title, message, type, confirmText, cancelText,
        onConfirm: onConfirm ?? null, onCancel: onCancel ?? null,
      },
    });
  },
  closeConfirm: () => {
    const { confirmModal } = get();
    const onCancel = confirmModal.onCancel;
    set({ confirmModal: INITIAL_CONFIRM });
    if (onCancel) onCancel();
  },
  handleConfirm: () => {
    const { confirmModal } = get();
    const onConfirm = confirmModal.onConfirm;
    set({ confirmModal: INITIAL_CONFIRM });
    if (onConfirm) onConfirm();
  },

  // UI visibility state
  showSettings: false,
  setShowSettings: (val) => set({ showSettings: val }),
  showShortcutsHelp: false,
  setShowShortcutsHelp: (val) => set((state) => ({
    showShortcutsHelp: typeof val === 'function' ? val(state.showShortcutsHelp) : val,
  })),
  rightPanelTab: 'sources',
  setRightPanelTab: (val) => set({ rightPanelTab: val }),
  leftSidebarCollapsed: false,
  setLeftSidebarCollapsed: (val) => set((state) => ({
    leftSidebarCollapsed: typeof val === 'function' ? val(state.leftSidebarCollapsed) : val,
  })),
  rightSidebarCollapsed: false,
  setRightSidebarCollapsed: (val) => set((state) => ({
    rightSidebarCollapsed: typeof val === 'function' ? val(state.rightSidebarCollapsed) : val,
  })),
  leftSidebarOpen: false,
  setLeftSidebarOpen: (val) => set({ leftSidebarOpen: val }),
  rightPanelOpen: false,
  setRightPanelOpen: (val) => set({ rightPanelOpen: val }),
  // Preview modal
  previewModal: { show: false, title: '', content: '' },
  setPreviewModal: (val) => set({ previewModal: val }),
}));
