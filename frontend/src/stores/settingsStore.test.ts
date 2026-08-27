import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  api: {
    updateSettings: vi.fn(),
    reindexDocuments: vi.fn(),
    getDocuments: vi.fn().mockResolvedValue({ documents: [] }),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

vi.mock('../utils/logger', () => ({ default: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { useSettingsStore, loadSavedRagSettings } from './settingsStore';
import { useUIStore } from './uiStore';
import { api } from '../api';

const defaultRagSettings = {
  vectorDb: 'chroma', indexName: 'casecite-legal-docs', embeddingModel: 'text-embedding-3-small',
  dimensions: 1536, chunkSize: 512, chunkOverlap: 128, similarityThreshold: 0.25,
  topK: 10, enableReranking: true, hybridSearch: true, citationVerification: true,
  contextCompression: false, queryExpansion: true, sourceTracking: true,
  llmModel: 'gpt-5.5', temperature: 0.1, maxTokens: 16384, batchSize: 100,
};

describe('settingsStore', () => {
  beforeEach(() => {
    useSettingsStore.setState(useSettingsStore.getInitialState(), true);
    useUIStore.setState(useUIStore.getInitialState(), true);
    vi.clearAllMocks();
    localStorage.clear();
  });

  // ==================== loadSavedRagSettings ====================

  it('loadSavedRagSettings returns defaults when no saved settings', () => {
    const settings = loadSavedRagSettings();
    expect(settings).toEqual(defaultRagSettings);
  });

  it('loadSavedRagSettings merges saved settings with defaults', () => {
    localStorage.setItem('wl_rag_settings', JSON.stringify({ topK: 20, llmModel: 'gpt-5.4-mini' }));
    const settings = loadSavedRagSettings();
    expect(settings.topK).toBe(20);
    expect(settings.llmModel).toBe('gpt-5.4-mini');
    expect(settings.vectorDb).toBe('chroma');
  });

  it('loadSavedRagSettings returns defaults on invalid JSON', () => {
    localStorage.setItem('wl_rag_settings', 'not valid json');
    const settings = loadSavedRagSettings();
    expect(settings).toEqual(defaultRagSettings);
  });

  // ==================== init (lazy hydration) ====================

  it('init hydrates ragSettings from localStorage', () => {
    localStorage.setItem('wl_rag_settings', JSON.stringify({ topK: 42 }));
    useSettingsStore.getState().init();
    expect(useSettingsStore.getState().ragSettings.topK).toBe(42);
    expect(useSettingsStore.getState()._initialized).toBe(true);
  });

  it('init is a no-op after the first call', () => {
    localStorage.setItem('wl_rag_settings', JSON.stringify({ topK: 42 }));
    useSettingsStore.getState().init();
    localStorage.setItem('wl_rag_settings', JSON.stringify({ topK: 7 }));
    useSettingsStore.getState().init();
    expect(useSettingsStore.getState().ragSettings.topK).toBe(42);
  });

  it('does not read localStorage before init', () => {
    localStorage.setItem('wl_rag_settings', JSON.stringify({ topK: 99 }));
    // State was reset in beforeEach; without init() the defaults must hold.
    expect(useSettingsStore.getState().ragSettings).toEqual(defaultRagSettings);
  });

  // ==================== Initial State ====================

  it('has correct initial state', () => {
    const state = useSettingsStore.getState();
    expect(state.ragSettings).toEqual(defaultRagSettings);
    expect(state.systemStats).toEqual({ totalDocuments: 0, totalEmbeddings: 0, isHealthy: true });
    expect(state.isReindexing).toBe(false);
    expect(state.isClearing).toBe(false);
  });

  // ==================== Setters ====================

  it('setRagSettings updates ragSettings', () => {
    const newSettings = { ...defaultRagSettings, topK: 25 };
    useSettingsStore.getState().setRagSettings(newSettings);
    expect(useSettingsStore.getState().ragSettings.topK).toBe(25);
  });

  it('setSystemStats updates systemStats with object', () => {
    useSettingsStore.getState().setSystemStats({ totalDocuments: 10, totalEmbeddings: 100, isHealthy: true });
    expect(useSettingsStore.getState().systemStats.totalDocuments).toBe(10);
  });

  it('setSystemStats supports functional update', () => {
    useSettingsStore.getState().setSystemStats((prev) => ({ ...prev, totalDocuments: prev.totalDocuments + 5 }));
    expect(useSettingsStore.getState().systemStats.totalDocuments).toBe(5);
  });

  it('setIsReindexing updates isReindexing', () => {
    useSettingsStore.getState().setIsReindexing(true);
    expect(useSettingsStore.getState().isReindexing).toBe(true);
  });

  it('setIsClearing updates isClearing', () => {
    useSettingsStore.getState().setIsClearing(true);
    expect(useSettingsStore.getState().isClearing).toBe(true);
  });

  // ==================== handleSaveSettings ====================

  it('handleSaveSettings saves settings locally and to backend', async () => {
    (api.updateSettings as ReturnType<typeof vi.fn>).mockResolvedValue({});

    const newSettings = { ...defaultRagSettings, topK: 20 };
    await useSettingsStore.getState().handleSaveSettings(newSettings);

    expect(useSettingsStore.getState().ragSettings.topK).toBe(20);
    expect(api.updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({ top_k: 20 })
    );
  });

  it('handleSaveSettings resolves true on success', async () => {
    (api.updateSettings as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await expect(
      useSettingsStore.getState().handleSaveSettings({ ...defaultRagSettings, topK: 20 })
    ).resolves.toBe(true);
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it('handleSaveSettings rolls back, toasts, and resolves false when the backend fails', async () => {
    (api.updateSettings as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Backend error'));
    useSettingsStore.setState({ ragSettings: { ...defaultRagSettings, topK: 5 } });

    const newSettings = { ...defaultRagSettings, topK: 30 };
    const ok = await useSettingsStore.getState().handleSaveSettings(newSettings);

    expect(ok).toBe(false);
    expect(useSettingsStore.getState().ragSettings.topK).toBe(5);
    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.type === 'error' && t.message.includes('Backend error'))).toBe(true);
  });

  // ==================== handleReindex ====================

  it('handleReindex reindexes and shows success toast', async () => {
    (api.reindexDocuments as ReturnType<typeof vi.fn>).mockResolvedValue({});

    await useSettingsStore.getState().handleReindex();

    expect(useSettingsStore.getState().isReindexing).toBe(false);
    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message === 'Reindex complete')).toBe(true);
  });

  it('handleReindex shows error toast on failure', async () => {
    (api.reindexDocuments as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Reindex error'));

    await useSettingsStore.getState().handleReindex();

    expect(useSettingsStore.getState().isReindexing).toBe(false);
    const toasts = useUIStore.getState().toasts;
    expect(toasts.some(t => t.message === 'Reindex failed')).toBe(true);
  });

});
