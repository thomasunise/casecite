import { useRef, useCallback, useState, useEffect, useId } from 'react';
import { api } from '../../../api';
import { useUIStore } from '../../../stores/uiStore';
import { Icon } from '../../shared/Icon';
import type { RagSettings } from '../../../types';
import type { CourtListenerStatus, LocalLlmStatus } from '../../../api/types';

interface APIKeysTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  showKeys: Record<string, boolean>;
  setShowKeys: (s: Record<string, boolean>) => void;
  apiKeys: Record<string, string>;
  setApiKeys: (keys: Record<string, string>) => void;
  serverKeyStatus: Record<string, boolean>;
  maskedKeys: Record<string, string | null>;
  keyStatusError: boolean;
  refreshKeyStatus: () => Promise<void>;
  s: Record<string, string>;
}

export const APIKeysTab = ({ local: _local, setLocal: _setLocal, showKeys, setShowKeys, apiKeys, setApiKeys, serverKeyStatus, maskedKeys, keyStatusError, refreshKeyStatus, s }: APIKeysTabProps) => {
  const id = useId();
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  // Values typed but not yet persisted (the debounce window). Flushed
  // immediately on blur and on unmount so closing the modal can never race
  // a pending save.
  const pendingSaves = useRef<Record<string, string>>({});
  const addToast = useUIStore((st) => st.addToast);
  const showConfirm = useUIStore((st) => st.showConfirm);

  // CourtListener instance token
  const [clStatus, setClStatus] = useState<CourtListenerStatus | null>(null);
  const [clToken, setClToken] = useState('');

  // Local / custom OpenAI-compatible model endpoint
  const [llmStatus, setLlmStatus] = useState<LocalLlmStatus | null>(null);
  const [baseUrl, setBaseUrl] = useState('');
  const [chatModel, setChatModel] = useState('');
  const [utilityModel, setUtilityModel] = useState('');

  const loadIntegrations = useCallback(async () => {
    try {
      setClStatus(await api.getCourtListenerStatus());
    } catch { /* non-critical */ }
    try {
      const llm = await api.getLocalLlmStatus();
      setLlmStatus(llm);
      setBaseUrl(llm.base_url || '');
      setChatModel(llm.chat_model || '');
      setUtilityModel(llm.utility_model || '');
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { loadIntegrations(); }, [loadIntegrations]);

  // Per-provider save state for the inline "Saving.../Saved" hint.
  const [savedState, setSavedState] = useState<Record<string, 'saving' | 'saved' | 'error'>>({});
  const markSaved = (key: string, state: 'saving' | 'saved' | 'error') =>
    setSavedState((prev) => ({ ...prev, [key]: state }));

  const saveKeyNow = useCallback(async (provider: string, value: string) => {
    delete pendingSaves.current[provider];
    markSaved(provider, 'saving');
    try {
      await api.saveApiKey(provider, value);
      markSaved(provider, 'saved');
      // Reflect the SERVER's truth immediately — the check mark and masked
      // hint must never depend on reopening the modal.
      await refreshKeyStatus();
    } catch (e) {
      markSaved(provider, 'error');
      addToast(e instanceof Error ? e.message : `Failed to save ${provider} key`, 'error');
    }
  }, [addToast, refreshKeyStatus]);

  const persistKeyToServer = useCallback((provider: string, value: string) => {
    if (saveTimers.current[provider]) clearTimeout(saveTimers.current[provider]);
    delete pendingSaves.current[provider];
    if (!value || value.length < 10) return;
    pendingSaves.current[provider] = value;
    markSaved(provider, 'saving');
    saveTimers.current[provider] = setTimeout(() => saveKeyNow(provider, value), 800);
  }, [saveKeyNow]);

  // Flush a provider's pending save immediately (field blur).
  const flushKeySave = useCallback((provider: string) => {
    const value = pendingSaves.current[provider];
    if (!value) return;
    if (saveTimers.current[provider]) clearTimeout(saveTimers.current[provider]);
    saveKeyNow(provider, value);
  }, [saveKeyNow]);

  // Closing the modal unmounts this tab — fire anything still pending so a
  // fast type-then-close never loses the key.
  useEffect(() => {
    const timers = saveTimers.current;
    const pending = pendingSaves.current;
    return () => {
      for (const provider of Object.keys(pending)) {
        if (timers[provider]) clearTimeout(timers[provider]);
        const value = pending[provider];
        if (value) api.saveApiKey(provider, value).catch(() => { /* surfaced on next open */ });
      }
    };
  }, []);

  const handleApiKeyChange = (provider: string, value: string) => {
    const updated = { ...apiKeys, [provider]: value };
    setApiKeys(updated);
    persistKeyToServer(provider, value);
  };

  // Small inline status shown next to each field's label.
  const SaveHint = ({ k }: { k: string }) => {
    const st = savedState[k];
    if (st === 'saving') return <span className={s.saveHint}>Saving…</span>;
    if (st === 'saved') return <span className={s.saveHintOk}><Icon name="Check" size={12} /> Saved</span>;
    if (st === 'error') return <span className={s.saveHintErr}><Icon name="AlertCircle" size={12} /> Failed</span>;
    return null;
  };

  // Helper: get the placeholder for a key field.
  // If a key is saved server-side, show masked hint; otherwise show format hint.
  const getPlaceholder = (provider: string, defaultHint: string) => {
    if (maskedKeys[provider]) return maskedKeys[provider]!;
    return defaultHint;
  };

  // Helper: check if a provider is configured (either locally entered or on server)
  const isConfigured = (provider: string) => apiKeys[provider] || serverKeyStatus[provider];

  // Unified status for every credential/endpoint on this page.
  const statusItems = [
    { key: 'openai', label: 'OpenAI', required: true, configured: !!isConfigured('openai') },
    { key: 'anthropic', label: 'Anthropic', required: false, configured: !!isConfigured('anthropic') },
    { key: 'google', label: 'Gemini', required: false, configured: !!isConfigured('google') },
    { key: 'voyage', label: 'Voyage', required: false, configured: !!isConfigured('voyage') },
    { key: 'cohere', label: 'Cohere', required: false, configured: !!isConfigured('cohere') },
    { key: 'courtlistener', label: 'CourtListener', required: false, configured: !!clStatus?.configured },
    { key: 'local', label: 'Local Model', required: false, configured: !!llmStatus?.configured },
  ];

  // ----- CourtListener handlers (auto-save, debounced) -----
  const clTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleClChange = (value: string) => {
    setClToken(value);
    if (clTimer.current) clearTimeout(clTimer.current);
    if (value.trim().length < 10) return;
    markSaved('courtlistener', 'saving');
    clTimer.current = setTimeout(async () => {
      try {
        setClStatus(await api.setCourtListenerToken(value.trim()));
        setClToken('');
        markSaved('courtlistener', 'saved');
      } catch (e) {
        markSaved('courtlistener', 'error');
        addToast(e instanceof Error ? e.message : 'Failed to save token', 'error');
      }
    }, 800);
  };

  const handleClearCl = () => {
    showConfirm({
      title: 'Clear CourtListener token',
      message: 'Clear the CourtListener token? Case law search reverts to the .env fallback (or anonymous, rate-limited).',
      confirmText: 'Clear',
      onConfirm: async () => {
        try {
          await api.clearCourtListenerToken();
          setClToken('');
          await loadIntegrations();
          addToast('CourtListener token cleared', 'success');
        } catch (e) {
          addToast(e instanceof Error ? e.message : 'Failed to clear token', 'error');
        }
      },
    });
  };

  // ----- Local model endpoint (auto-save, debounced) -----
  const llmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoSaveLlm = (next: { baseUrl: string; chatModel: string; utilityModel: string }) => {
    if (llmTimer.current) clearTimeout(llmTimer.current);
    // Needs both a base URL and a chat model to be a valid endpoint.
    if (next.baseUrl.trim().length < 4 || !next.chatModel.trim()) return;
    markSaved('local', 'saving');
    llmTimer.current = setTimeout(async () => {
      try {
        setLlmStatus(await api.setLocalLlm({
          baseUrl: next.baseUrl.trim(),
          chatModel: next.chatModel.trim(),
          utilityModel: next.utilityModel.trim() || null,
        }));
        markSaved('local', 'saved');
      } catch (e) {
        markSaved('local', 'error');
        addToast(e instanceof Error ? e.message : 'Failed to save endpoint', 'error');
      }
    }, 1000);
  };

  const handleClearLlm = () => {
    showConfirm({
      title: 'Revert to OpenAI',
      message: 'Remove the local endpoint and revert to the default OpenAI models?',
      confirmText: 'Revert',
      onConfirm: async () => {
        try {
          await api.clearLocalLlm();
          await loadIntegrations();
          addToast('Reverted to default models', 'success');
        } catch (e) {
          addToast(e instanceof Error ? e.message : 'Failed to revert', 'error');
        }
      },
    });
  };

  return (
    <div className={s.settingsGrid}>
      {/* Key Status — kept at the top so configuration state is visible at a glance */}
      <div className={s.keyStatusSection}>
        <div className={s.keyStatusTitle}>Key Status</div>
        <div className={s.keyStatusList}>
          {statusItems.map((item) => (
            <div key={item.key} className={`${s.keyBadge} ${item.configured ? s.keyBadgeActive : (item.required ? s.keyBadgeRequired : s.keyBadgeOptional)}`}>
              <Icon name={item.configured ? 'Check' : (item.required ? 'AlertCircle' : 'Minus')} size={12} />
              {item.label}
            </div>
          ))}
        </div>
      </div>

      {keyStatusError && (
        <div className={s.byokBanner}>
          <div className={s.bannerHeader}>
            <Icon name="AlertCircle" size={16} className={s.bannerIconAmber} />
            <span className={s.bannerTitleBlue}>Could not load saved-key status</span>
          </div>
          <p className={s.bannerTextBlue}>
            The fields below may show as unconfigured even though your keys are still saved on the
            server. Reopen Settings to retry — do not re-enter keys unless a provider genuinely
            stops working.
          </p>
        </div>
      )}

      <div className={s.byokBanner}>
        <div className={s.bannerHeader}>
          <Icon name="Key" size={16} className={s.bannerIconBlue} />
          <span className={s.bannerTitleBlue}>Bring Your Own Keys</span>
        </div>
        <p className={s.bannerTextBlue}>
          Your API keys are encrypted and stored securely on our servers. Keys are never exposed in API responses.
          {Object.values(serverKeyStatus).some(Boolean) && ' Saved keys are shown masked below — leave a field empty to keep your existing key.'}
        </p>
      </div>

      {/* ===== Case Law ===== */}
      <div className={s.sectionTitle}>
        <Icon name="Scale" size={13} /> Case Law
      </div>

      <div className={s.settingGroupFullWidth}>
        <label className={s.settingLabel} htmlFor={`${id}-key-courtlistener`}>
          <span className={s.labelFlex}>
            CourtListener API Token
            {clStatus?.configured && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="courtlistener" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-courtlistener`}
            type={showKeys.courtlistener ? 'text' : 'password'}
            className={s.modalInputMono}
            value={clToken}
            onChange={e => handleClChange(e.target.value)}
            placeholder={clStatus?.masked || 'Free Law Project API token'}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({ ...showKeys, courtlistener: !showKeys.courtlistener })}
          >
            <Icon name={showKeys.courtlistener ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>
          {clStatus?.configured
            ? `Configured (source: ${clStatus.source}). Powers every Legal Tool. Type a new token to replace it — saves automatically.`
            : 'Powers every Legal Tool (case search, judges, dockets, precedents). Paste your token — it saves automatically. Get one free at courtlistener.com.'}
        </span>
        {clStatus?.configured && clStatus.source === 'instance' && (
          <div className={s.boxActions}>
            <button className={s.brandingResetBtn} onClick={handleClearCl}>Clear</button>
          </div>
        )}
      </div>

      {/* ===== Language Models ===== */}
      <div className={s.sectionTitle}>
        <Icon name="Sparkles" size={13} /> Language Models (LLMs)
      </div>

      {/* OpenAI */}
      <div className={s.settingGroupFullWidth}>
        <label className={s.settingLabel} htmlFor={`${id}-key-openai`}>
          <span className={s.labelFlex}>
            <span className={`${s.providerIcon} ${s.providerIconOpenAI}`}>
              <span className={s.providerIconText}>AI</span>
            </span>
            OpenAI API Key
            {isConfigured('openai') && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="openai" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-openai`}
            type={showKeys.openai ? 'text' : 'password'}
            className={s.modalInputMono}
            value={apiKeys.openai}
            onChange={e => handleApiKeyChange('openai', e.target.value)}
            onBlur={() => flushKeySave('openai')}
            placeholder={getPlaceholder('openai', 'sk-...')}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({...showKeys, openai: !showKeys.openai})}
          >
            <Icon name={showKeys.openai ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>Used for GPT-5 and default embeddings. Get key at platform.openai.com</span>
      </div>

      {/* Anthropic */}
      <div className={s.settingGroupFullWidth}>
        <label className={s.settingLabel} htmlFor={`${id}-key-anthropic`}>
          <span className={s.labelFlex}>
            <span className={`${s.providerIcon} ${s.providerIconAnthropic}`}>
              <span className={s.providerIconTextSmall}>A</span>
            </span>
            Anthropic API Key
            {isConfigured('anthropic') && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="anthropic" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-anthropic`}
            type={showKeys.anthropic ? 'text' : 'password'}
            className={s.modalInputMono}
            value={apiKeys.anthropic}
            onChange={e => handleApiKeyChange('anthropic', e.target.value)}
            onBlur={() => flushKeySave('anthropic')}
            placeholder={getPlaceholder('anthropic', 'sk-ant-...')}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({...showKeys, anthropic: !showKeys.anthropic})}
          >
            <Icon name={showKeys.anthropic ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>Used for Claude models. Get key at console.anthropic.com</span>
      </div>

      {/* Google Gemini */}
      <div className={s.settingGroupFullWidth}>
        <label className={s.settingLabel} htmlFor={`${id}-key-google`}>
          <span className={s.labelFlex}>
            <span className={`${s.providerIcon} ${s.providerIconGoogle}`}>
              <span className={s.providerIconTextSmall}>G</span>
            </span>
            Google Gemini API Key
            {isConfigured('google') && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="google" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-google`}
            type={showKeys.google ? 'text' : 'password'}
            className={s.modalInputMono}
            value={apiKeys.google}
            onChange={e => handleApiKeyChange('google', e.target.value)}
            onBlur={() => flushKeySave('google')}
            placeholder={getPlaceholder('google', 'AIza...')}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({...showKeys, google: !showKeys.google})}
          >
            <Icon name={showKeys.google ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>Used for Gemini models. Get key at aistudio.google.com</span>
      </div>

      {/* ===== Embeddings ===== */}
      <div className={s.sectionTitle}>
        <Icon name="Layers" size={13} /> Embedding Models
      </div>
      <div className={s.sectionSubtext}>
        Dedicated embedding providers for vector search. OpenAI (above) supplies the default embeddings.
      </div>

      {/* Voyage */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-key-voyage`}>
          <span className={s.labelFlex}>
            Voyage AI Key
            {isConfigured('voyage') && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="voyage" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-voyage`}
            type={showKeys.voyage ? 'text' : 'password'}
            className={s.modalInputMono}
            value={apiKeys.voyage}
            onChange={e => handleApiKeyChange('voyage', e.target.value)}
            onBlur={() => flushKeySave('voyage')}
            placeholder={getPlaceholder('voyage', 'pa-...')}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({...showKeys, voyage: !showKeys.voyage})}
          >
            <Icon name={showKeys.voyage ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>Legal-optimized embeddings (voyage-law-2)</span>
      </div>

      {/* Cohere */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-key-cohere`}>
          <span className={s.labelFlex}>
            Cohere API Key
            {isConfigured('cohere') && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
            <SaveHint k="cohere" />
          </span>
        </label>
        <div className={s.inputRow}>
          <input
            id={`${id}-key-cohere`}
            type={showKeys.cohere ? 'text' : 'password'}
            className={s.modalInputMono}
            value={apiKeys.cohere}
            onChange={e => handleApiKeyChange('cohere', e.target.value)}
            onBlur={() => flushKeySave('cohere')}
            placeholder={getPlaceholder('cohere', '...')}
          />
          <button
            className={s.btnSecondarySmall}
            onClick={() => setShowKeys({...showKeys, cohere: !showKeys.cohere})}
          >
            <Icon name={showKeys.cohere ? 'EyeOff' : 'Eye'} size={16} />
          </button>
        </div>
        <span className={s.helpText}>Alternative embeddings provider</span>
      </div>

      {/* ===== Local / Self-Hosted (highlighted box) ===== */}
      <div className={s.localModelBox}>
        <div className={s.localModelHeader}>
          <Icon name="Server" size={16} className={s.bannerIconAmber} />
          <span className={s.localModelTitle}>Local / Self-Hosted Model</span>
          {llmStatus?.configured && <Icon name="CheckCircle" size={14} className={s.checkIcon} />}
          <SaveHint k="local" />
        </div>
        <p className={s.localModelDesc}>
          Point the app at any OpenAI-compatible endpoint — Ollama, LM Studio, vLLM, or hosted gateways
          (Together, Groq, OpenRouter). Leave blank to use the default OpenAI models above.
        </p>

        <div>
          <label className={s.settingLabel} htmlFor={`${id}-llm-base-url`}>Base URL</label>
          <input
            id={`${id}-llm-base-url`}
            className={s.modalInputMono}
            value={baseUrl}
            onChange={e => { const v = e.target.value; setBaseUrl(v); autoSaveLlm({ baseUrl: v, chatModel, utilityModel }); }}
            placeholder="http://localhost:11434/v1"
          />
        </div>

        <div>
          <label className={s.settingLabel} htmlFor={`${id}-llm-chat-model`}>Chat Model</label>
          <input
            id={`${id}-llm-chat-model`}
            className={s.modalInputMono}
            value={chatModel}
            onChange={e => { const v = e.target.value; setChatModel(v); autoSaveLlm({ baseUrl, chatModel: v, utilityModel }); }}
            placeholder="llama3.1:70b"
          />
        </div>

        <div>
          <label className={s.settingLabel} htmlFor={`${id}-llm-utility-model`}>Utility Model (optional)</label>
          <input
            id={`${id}-llm-utility-model`}
            className={s.modalInputMono}
            value={utilityModel}
            onChange={e => { const v = e.target.value; setUtilityModel(v); autoSaveLlm({ baseUrl, chatModel, utilityModel: v }); }}
            placeholder="defaults to chat model"
          />
        </div>

        {llmStatus?.configured && (
          <div className={s.boxActions}>
            <button className={s.brandingResetBtn} onClick={handleClearLlm}>Revert to OpenAI</button>
          </div>
        )}
      </div>

    </div>
  );
};
