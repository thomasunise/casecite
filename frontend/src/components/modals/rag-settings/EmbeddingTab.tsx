import { useId } from 'react';
import type { RagSettings } from '../../../types';

interface EmbeddingTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  s: Record<string, string>;
}

export const EmbeddingTab = ({ local, setLocal, s }: EmbeddingTabProps) => {
  const id = useId();
  return (
  <div className={s.settingsGrid}>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-embedding-model`}>Embedding Model</label>
      <select id={`${id}-embedding-model`} className={s.select} value={local.embeddingModel} onChange={e => setLocal({...local, embeddingModel: e.target.value})}>
        <option value="text-embedding-3-large">OpenAI text-embedding-3-large (3072d)</option>
        <option value="text-embedding-3-small">OpenAI text-embedding-3-small (1536d)</option>
        <option value="voyage-law-2">Voyage AI voyage-law-2 (1024d)</option>
        <option value="cohere-embed-v3">Cohere embed-v3 (1024d)</option>
      </select>
    </div>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-dimensions`}>Embedding Dimensions</label>
      <input id={`${id}-dimensions`} type="number" className={s.modalInput} value={local.dimensions} onChange={e => setLocal({...local, dimensions: parseInt(e.target.value)})} />
    </div>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-batch-size`}>Batch Size</label>
      <input id={`${id}-batch-size`} type="number" className={s.modalInput} value={local.batchSize || 100} onChange={e => setLocal({...local, batchSize: parseInt(e.target.value)})} />
    </div>
  </div>
  );
};
