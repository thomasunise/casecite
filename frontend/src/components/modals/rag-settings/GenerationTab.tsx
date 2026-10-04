import { useId } from 'react';
import type { RagSettings } from '../../../types';

interface GenerationTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  s: Record<string, string>;
}

export const GenerationTab = ({ local, setLocal, s }: GenerationTabProps) => {
  const id = useId();
  return (
  <div className={s.settingsGrid}>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-llm-model`}>LLM Model</label>
      <select id={`${id}-llm-model`} className={s.select} value={local.llmModel || 'gpt-5.5'} onChange={e => setLocal({...local, llmModel: e.target.value})}>
        <optgroup label="OpenAI">
          <option value="gpt-5.5">GPT-5.5 (Recommended)</option>
          <option value="gpt-5.4-mini">GPT-5.4 Mini (Fast)</option>
        </optgroup>
        <optgroup label="Anthropic">
          <option value="claude-opus-4-8">Claude Opus 4.8</option>
          <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
          <option value="claude-haiku-4-5">Claude Haiku 4.5 (Fast)</option>
        </optgroup>
        <optgroup label="Google">
          <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro</option>
        </optgroup>
      </select>
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-temperature`}>Temperature</label>
        <span className={`${s.sliderValue} mono`}>{(local.temperature ?? 0.1).toFixed(2)}</span>
      </div>
      {/* `??`, not `||`: 0 (fully deterministic) is a valid choice. */}
      <input id={`${id}-temperature`} type="range" min="0" max="1" step="0.05" value={local.temperature ?? 0.1} onChange={e => setLocal({...local, temperature: parseFloat(e.target.value)})} />
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-max-tokens`}>Max Tokens</label>
        <span className={`${s.sliderValue} mono`}>{local.maxTokens || 4096}</span>
      </div>
      {/* 4096 is the server default; the range covers values saved by earlier builds. */}
      <input id={`${id}-max-tokens`} type="range" min="1024" max="32768" step="512" value={local.maxTokens || 4096} onChange={e => setLocal({...local, maxTokens: parseInt(e.target.value)})} />
    </div>
  </div>
  );
};
