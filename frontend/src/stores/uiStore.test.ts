import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../utils', () => ({
  generateId: vi.fn(() => 'test-id-' + Math.random().toString(36).slice(2, 8)),
}));

import { useUIStore } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => {
    useUIStore.setState(useUIStore.getInitialState(), true);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ==================== Initial State ====================

  it('has correct initial state', () => {
    const state = useUIStore.getState();
    expect(state.toasts).toEqual([]);
    expect(state.confirmModal.open).toBe(false);
    expect(state.confirmModal.title).toBe('');
    expect(state.confirmModal.message).toBe('');
    expect(state.confirmModal.type).toBe('info');
    expect(state.confirmModal.confirmText).toBe('Confirm');
    expect(state.confirmModal.cancelText).toBe('Cancel');
    expect(state.confirmModal.onConfirm).toBeNull();
    expect(state.confirmModal.onCancel).toBeNull();
    expect(state.showSettings).toBe(false);
    expect(state.showShortcutsHelp).toBe(false);
    expect(state.rightPanelTab).toBe('sources');
    expect(state.leftSidebarCollapsed).toBe(false);
    expect(state.rightSidebarCollapsed).toBe(false);
  });

  // ==================== Toast Operations ====================

  it('addToast adds a toast', () => {
    useUIStore.getState().addToast('Test message', 'success');
    expect(useUIStore.getState().toasts).toHaveLength(1);
    expect(useUIStore.getState().toasts[0].message).toBe('Test message');
    expect(useUIStore.getState().toasts[0].type).toBe('success');
  });

  it('addToast defaults type to info', () => {
    useUIStore.getState().addToast('Info message');
    expect(useUIStore.getState().toasts[0].type).toBe('info');
  });

  it('addToast auto-removes toast after 4 seconds', () => {
    useUIStore.getState().addToast('Temporary message', 'info');
    expect(useUIStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(4000);
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it('addToast can add multiple toasts', () => {
    useUIStore.getState().addToast('First', 'info');
    useUIStore.getState().addToast('Second', 'error');
    expect(useUIStore.getState().toasts).toHaveLength(2);
  });

  // ==================== Confirm Modal ====================

  it('showConfirm opens the confirm modal with options', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    useUIStore.getState().showConfirm({
      title: 'Delete?',
      message: 'Are you sure?',
      type: 'warning',
      confirmText: 'Yes, delete',
      cancelText: 'No',
      onConfirm,
      onCancel,
    });

    const modal = useUIStore.getState().confirmModal;
    expect(modal.open).toBe(true);
    expect(modal.title).toBe('Delete?');
    expect(modal.message).toBe('Are you sure?');
    expect(modal.type).toBe('warning');
    expect(modal.confirmText).toBe('Yes, delete');
    expect(modal.cancelText).toBe('No');
    expect(modal.onConfirm).toBe(onConfirm);
    expect(modal.onCancel).toBe(onCancel);
  });

  it('showConfirm uses default type, confirmText, cancelText', () => {
    useUIStore.getState().showConfirm({ title: 'Test', message: 'Test message' });

    const modal = useUIStore.getState().confirmModal;
    expect(modal.type).toBe('danger');
    expect(modal.confirmText).toBe('Confirm');
    expect(modal.cancelText).toBe('Cancel');
  });

  it('handleConfirm calls onConfirm and resets modal', () => {
    const onConfirm = vi.fn();
    useUIStore.getState().showConfirm({ title: 'Test', message: 'Test', onConfirm });

    useUIStore.getState().handleConfirm();

    expect(onConfirm).toHaveBeenCalled();
    expect(useUIStore.getState().confirmModal.open).toBe(false);
  });

  it('closeConfirm calls onCancel and resets modal', () => {
    const onCancel = vi.fn();
    useUIStore.getState().showConfirm({ title: 'Test', message: 'Test', onCancel });

    useUIStore.getState().closeConfirm();

    expect(onCancel).toHaveBeenCalled();
    expect(useUIStore.getState().confirmModal.open).toBe(false);
  });

  it('closeConfirm works when no onCancel provided', () => {
    useUIStore.getState().showConfirm({ title: 'Test', message: 'Test' });
    useUIStore.getState().closeConfirm();
    expect(useUIStore.getState().confirmModal.open).toBe(false);
  });

  it('handleConfirm works when no onConfirm provided', () => {
    useUIStore.getState().showConfirm({ title: 'Test', message: 'Test' });
    useUIStore.getState().handleConfirm();
    expect(useUIStore.getState().confirmModal.open).toBe(false);
  });

  // ==================== UI Visibility Setters ====================

  it('setShowSettings updates showSettings', () => {
    useUIStore.getState().setShowSettings(true);
    expect(useUIStore.getState().showSettings).toBe(true);
  });


  it('setShowShortcutsHelp updates showShortcutsHelp with boolean', () => {
    useUIStore.getState().setShowShortcutsHelp(true);
    expect(useUIStore.getState().showShortcutsHelp).toBe(true);
  });

  it('setShowShortcutsHelp supports functional toggle', () => {
    useUIStore.getState().setShowShortcutsHelp(true);
    useUIStore.getState().setShowShortcutsHelp((prev) => !prev);
    expect(useUIStore.getState().showShortcutsHelp).toBe(false);
  });

  it('setRightPanelTab updates rightPanelTab', () => {
    useUIStore.getState().setRightPanelTab('documents');
    expect(useUIStore.getState().rightPanelTab).toBe('documents');
  });

  it('setLeftSidebarCollapsed updates with boolean', () => {
    useUIStore.getState().setLeftSidebarCollapsed(true);
    expect(useUIStore.getState().leftSidebarCollapsed).toBe(true);
  });

  it('setLeftSidebarCollapsed supports functional toggle', () => {
    useUIStore.getState().setLeftSidebarCollapsed(false);
    useUIStore.getState().setLeftSidebarCollapsed((prev) => !prev);
    expect(useUIStore.getState().leftSidebarCollapsed).toBe(true);
  });

  it('setRightSidebarCollapsed updates with boolean', () => {
    useUIStore.getState().setRightSidebarCollapsed(true);
    expect(useUIStore.getState().rightSidebarCollapsed).toBe(true);
  });

  it('setRightSidebarCollapsed supports functional toggle', () => {
    useUIStore.getState().setRightSidebarCollapsed(false);
    useUIStore.getState().setRightSidebarCollapsed((prev) => !prev);
    expect(useUIStore.getState().rightSidebarCollapsed).toBe(true);
  });

});
