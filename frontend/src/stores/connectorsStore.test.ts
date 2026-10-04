import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  api: {
    getConnectors: vi.fn(),
    getPickerConfig: vi.fn(),
    connectConnector: vi.fn(),
    disconnectConnector: vi.fn(),
    syncConnector: vi.fn(),
    getConnectorStatus: vi.fn(),
    importFromGooglePicker: vi.fn(),
    importFromOneDrivePicker: vi.fn(),
    importFromBoxPicker: vi.fn(),
    importFromDropboxChooser: vi.fn(),
    getDocuments: vi.fn(),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

vi.mock('../utils/logger', () => ({ default: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { useConnectorsStore } from './connectorsStore';
import { usePickerStore } from './pickerStore';
import { useUIStore } from './uiStore';
import { useDocumentsStore } from './documentsStore';
import { useAuthStore } from './authStore';
import { api } from '../api';

describe('connectorsStore', () => {
  beforeEach(() => {
    useConnectorsStore.setState(useConnectorsStore.getInitialState(), true);
    usePickerStore.setState(usePickerStore.getInitialState(), true);
    useUIStore.setState(useUIStore.getInitialState(), true);
    useDocumentsStore.setState(useDocumentsStore.getInitialState(), true);
    vi.clearAllMocks();
  });

  // ==================== Initial State ====================

  it('has correct initial state', () => {
    const state = useConnectorsStore.getState();
    expect(state.connectors).toHaveLength(8);
    expect(state.connectors[0].id).toBe('google_drive');
    expect(state.connectors[0].connected).toBe(false);
    expect(state.pickerConfig).toBeNull();
    expect(state.showPickerModal).toBe(false);
    expect(state.pickerLoading).toBe(false);
    expect(state.activePickerProvider).toBeNull();
  });

  // ==================== Setters ====================

  it('setConnectors replaces connectors with array', () => {
    const newConnectors = [{ id: 'test', name: 'Test', icon: 'X', color: '#000', connected: true, docs: 5 }];
    useConnectorsStore.getState().setConnectors(newConnectors as any);
    expect(useConnectorsStore.getState().connectors).toEqual(newConnectors);
  });

  it('setConnectors supports functional update', () => {
    useConnectorsStore.getState().setConnectors((prev) => prev.map(c => c.id === 'google_drive' ? { ...c, connected: true } : c));
    const google = useConnectorsStore.getState().connectors.find(c => c.id === 'google_drive');
    expect(google?.connected).toBe(true);
  });

  it('setPickerConfig updates pickerConfig', () => {
    const config = { google_enabled: true, microsoft_enabled: false } as any;
    useConnectorsStore.getState().setPickerConfig(config);
    expect(useConnectorsStore.getState().pickerConfig).toEqual(config);
  });

  it('setShowPickerModal updates showPickerModal', () => {
    useConnectorsStore.getState().setShowPickerModal(true);
    expect(useConnectorsStore.getState().showPickerModal).toBe(true);
  });

  it('setPickerLoading updates pickerLoading', () => {
    useConnectorsStore.getState().setPickerLoading(true);
    expect(useConnectorsStore.getState().pickerLoading).toBe(true);
  });

  it('setActivePickerProvider updates activePickerProvider', () => {
    useConnectorsStore.getState().setActivePickerProvider('google_drive');
    expect(useConnectorsStore.getState().activePickerProvider).toBe('google_drive');
  });

  // ==================== hasPickerSupport ====================

  it('hasPickerSupport returns false when pickerConfig is null', () => {
    expect(useConnectorsStore.getState().hasPickerSupport('google_drive')).toBe(false);
  });

  it('hasPickerSupport returns true for enabled provider', () => {
    useConnectorsStore.setState({
      pickerConfig: { google_enabled: true, microsoft_enabled: false } as any,
    });
    expect(useConnectorsStore.getState().hasPickerSupport('google_drive')).toBe(true);
    expect(useConnectorsStore.getState().hasPickerSupport('onedrive')).toBe(false);
  });

  it('hasPickerSupport returns false for unknown provider', () => {
    useConnectorsStore.setState({
      pickerConfig: { google_enabled: true, microsoft_enabled: true } as any,
    });
    expect(useConnectorsStore.getState().hasPickerSupport('imanage')).toBe(false);
  });

  // ==================== handlePickerFilesSelected ====================

  it('handlePickerFilesSelected does nothing for empty files', async () => {
    await useConnectorsStore.getState().handlePickerFilesSelected([], 'google');
    expect(api.importFromGooglePicker).not.toHaveBeenCalled();
  });

  it('handlePickerFilesSelected imports files from google and shows toast', async () => {
    (api.importFromGooglePicker as ReturnType<typeof vi.fn>).mockResolvedValue({ imported: 2, failed: 0 });
    (api.getDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({ documents: [{ id: '1' }] });

    const files = [{ id: '1', name: 'test.pdf' }] as any;
    await useConnectorsStore.getState().handlePickerFilesSelected(files, 'google');

    expect(api.importFromGooglePicker).toHaveBeenCalled();
    expect(useConnectorsStore.getState().pickerLoading).toBe(false);
  });

  it('handlePickerFilesSelected shows error toast for failed imports', async () => {
    (api.importFromOneDrivePicker as ReturnType<typeof vi.fn>).mockResolvedValue({ imported: 1, failed: 2 });
    (api.getDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({ documents: [] });

    const files = [{ id: '1', name: 'test.pdf' }] as any;
    await useConnectorsStore.getState().handlePickerFilesSelected(files, 'onedrive');

    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message.includes('Failed to import'))).toBe(true);
  });

  it('handlePickerFilesSelected handles unknown provider', async () => {
    const files = [{ id: '1', name: 'test.pdf' }] as any;
    await useConnectorsStore.getState().handlePickerFilesSelected(files, 'unknown_provider');

    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message.includes('Failed to import files'))).toBe(true);
    expect(useConnectorsStore.getState().pickerLoading).toBe(false);
  });

  // ==================== handleConnectorClick ====================

  it('handleConnectorClick shows error for unconfigured connector', async () => {
    const connector = { id: 'imanage', name: 'iManage', configured: false, connected: false } as any;
    await useConnectorsStore.getState().handleConnectorClick(connector);

    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message.includes('not configured'))).toBe(true);
  });

  it('handleConnectorClick opens picker modal for supported picker provider', async () => {
    useConnectorsStore.setState({
      pickerConfig: { google_enabled: true, microsoft_enabled: false } as any,
    });

    const connector = { id: 'google_drive', name: 'Google Drive', configured: true, connected: false } as any;
    await useConnectorsStore.getState().handleConnectorClick(connector);

    expect(useConnectorsStore.getState().activePickerProvider).toBe('google_drive');
    expect(useConnectorsStore.getState().showPickerModal).toBe(true);
  });

  it('never starts a whole-account sync without a second, explicit confirmation', async () => {
    (api.syncConnector as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 'started' });
    const connector = { id: 'clio', name: 'Clio', configured: true, connected: true } as any;

    await useConnectorsStore.getState().handleConnectorClick(connector);
    expect(useUIStore.getState().confirmModal.title).toBe('Manage Clio');

    // "Sync Now" only opens the scope warning — nothing is sent yet.
    useUIStore.getState().handleConfirm();
    expect(api.syncConnector).not.toHaveBeenCalled();
    const warning = useUIStore.getState().confirmModal;
    expect(warning.open).toBe(true);
    expect(warning.title).toBe('Import the entire Clio account?');
    expect(warning.message).toMatch(/Every document/);
    expect(warning.message).toMatch(/embedding provider/);
    expect(warning.confirmText).toBe('Import entire account');

    useUIStore.getState().handleConfirm();
    await vi.waitFor(() => expect(api.syncConnector).toHaveBeenCalledWith('clio', { sync_all: true }));
  });

  it('cancelling the whole-account warning sends nothing', async () => {
    const connector = { id: 'box', name: 'Box', configured: true, connected: true } as any;
    await useConnectorsStore.getState().handleConnectorClick(connector);
    useUIStore.getState().handleConfirm();
    useUIStore.getState().closeConfirm();
    expect(api.syncConnector).not.toHaveBeenCalled();
  });

  it('an admin-only connector is refused for a non-admin, and usable by an admin', async () => {
    const connector = { id: 'filevine', name: 'Filevine', configured: true, connected: true, adminOnly: true } as any;

    useAuthStore.setState({ user: { id: 'u1', email: 'a@firm.com', roles: ['attorney'] }, isAuthenticated: true });
    await useConnectorsStore.getState().handleConnectorClick(connector);
    expect(useUIStore.getState().confirmModal.open).toBe(false);
    expect(useUIStore.getState().toasts.some(t => t.message.includes('only an administrator'))).toBe(true);

    useAuthStore.setState({ user: { id: 'u2', email: 'admin@firm.com', roles: ['admin'] }, isAuthenticated: true });
    await useConnectorsStore.getState().handleConnectorClick(connector);
    expect(useUIStore.getState().confirmModal.title).toBe('Manage Filevine');
  });

  it('loadConnectors carries the admin_only flag', async () => {
    (api.getConnectors as ReturnType<typeof vi.fn>).mockResolvedValue({
      connectors: [{ id: 'filevine', connected: false, configured: true, admin_only: true }],
    });
    (api.getPickerConfig as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await useConnectorsStore.getState().loadConnectors();
    const filevine = useConnectorsStore.getState().connectors.find(c => c.id === 'filevine');
    expect(filevine?.adminOnly).toBe(true);
  });

  it('refuses to open an OAuth address that only looks like a provider', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    (api.connectConnector as ReturnType<typeof vi.fn>).mockResolvedValue({
      auth_url: 'https://app.clio.com.attacker.example/oauth',
    });
    const connector = { id: 'clio', name: 'Clio', configured: true, connected: false } as any;

    await useConnectorsStore.getState().handleConnectorClick(connector);

    expect(open).not.toHaveBeenCalled();
    expect(useUIStore.getState().toasts.some(t => t.message.includes('unexpected sign-in address'))).toBe(true);
    open.mockRestore();
  });

  it('checks the connection only after the OAuth popup has closed', async () => {
    vi.useFakeTimers();
    const popup = { closed: false } as Window;
    const open = vi.spyOn(window, 'open').mockReturnValue(popup);
    (api.connectConnector as ReturnType<typeof vi.fn>).mockResolvedValue({ auth_url: 'https://app.clio.com/oauth/authorize' });
    (api.getConnectorStatus as ReturnType<typeof vi.fn>).mockResolvedValue({ connected: true, docs_indexed: 3 });
    const connector = { id: 'clio', name: 'Clio', configured: true, connected: false } as any;

    const pending = useConnectorsStore.getState().handleConnectorClick(connector);
    await vi.advanceTimersByTimeAsync(5000);
    expect(api.getConnectorStatus).not.toHaveBeenCalled();

    (popup as { closed: boolean }).closed = true;
    await vi.advanceTimersByTimeAsync(1000);
    await pending;

    expect(api.getConnectorStatus).toHaveBeenCalledWith('clio');
    expect(useConnectorsStore.getState().connectors.find(c => c.id === 'clio')?.connected).toBe(true);
    open.mockRestore();
    vi.useRealTimers();
  });

  // ==================== openActivePicker ====================

  it('openActivePicker routes box to the Box picker (unconfigured shows config toast)', () => {
    useConnectorsStore.setState({ activePickerProvider: 'box' });
    useConnectorsStore.getState().openActivePicker();

    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message.includes('Box picker not configured'))).toBe(true);
    expect(toasts.some(t => t.message.includes('coming soon'))).toBe(false);
    expect(useConnectorsStore.getState().showPickerModal).toBe(false);
  });

  it('openActivePicker shows error for unknown provider', () => {
    useConnectorsStore.setState({ activePickerProvider: 'unknown' });
    useConnectorsStore.getState().openActivePicker();

    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message.includes('Picker not available'))).toBe(true);
  });

  // ==================== loadConnectors ====================

  it('loadConnectors fetches connectors and picker config', async () => {
    (api.getConnectors as ReturnType<typeof vi.fn>).mockResolvedValue({
      connectors: [{ id: 'google_drive', connected: true, configured: true, docs_indexed: 10 }],
    });
    (api.getPickerConfig as ReturnType<typeof vi.fn>).mockResolvedValue({ google_enabled: true, microsoft_enabled: false });

    await useConnectorsStore.getState().loadConnectors();

    const google = useConnectorsStore.getState().connectors.find(c => c.id === 'google_drive');
    expect(google?.connected).toBe(true);
    expect(google?.docs).toBe(10);
    expect(useConnectorsStore.getState().pickerConfig).toEqual({ google_enabled: true, microsoft_enabled: false });
  });

  it('loadConnectors handles connector API error gracefully', async () => {
    (api.getConnectors as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    (api.getPickerConfig as ReturnType<typeof vi.fn>).mockResolvedValue({ google_enabled: false, microsoft_enabled: false });

    await useConnectorsStore.getState().loadConnectors();

    // Should not throw; connectors remain at defaults
    expect(useConnectorsStore.getState().connectors).toHaveLength(8);
  });

  it('loadConnectors handles picker config API error gracefully', async () => {
    (api.getConnectors as ReturnType<typeof vi.fn>).mockResolvedValue({ connectors: [] });
    (api.getPickerConfig as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Picker error'));

    await useConnectorsStore.getState().loadConnectors();

    // pickerConfig should remain null from initial
    expect(useConnectorsStore.getState().pickerConfig).toBeNull();
  });
});
