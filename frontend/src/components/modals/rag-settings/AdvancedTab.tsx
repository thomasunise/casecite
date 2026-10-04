import { useSettingsStore } from '../../../stores/settingsStore';
import { Icon } from '../../shared/Icon';
import type { RagSettings } from '../../../types';

interface AdvancedTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  s: Record<string, string>;
}

export const AdvancedTab = ({ local, setLocal, s }: AdvancedTabProps) => {
  const { isReindexing, handleReindex } = useSettingsStore();

  return (
  <div className={s.toggleList}>
    {[
      { key: 'enableReranking', label: 'Cross-Encoder Reranking', desc: 'Rerank retrieved passages with a cross-encoder model. Takes effect only when the server has the optional sentence-transformers package installed; otherwise it is ignored and results keep their similarity order.' },
      { key: 'hybridSearch', label: 'Keyword Rescoring (BM25)', desc: 'Blend keyword-match scores into the ranking of the passages that semantic search retrieved' },
      { key: 'citationVerification', label: 'Citation Verification', desc: 'Cross-reference citations against source documents' },
      { key: 'contextCompression', label: 'Context Compression', desc: 'Compress retrieved context to fit more documents' },
      { key: 'queryExpansion', label: 'Query Expansion', desc: 'Automatically expand queries with related terms' },
      { key: 'sourceTracking', label: 'Source Tracking', desc: 'Track exact source locations for all citations' },
    ].map((item: { key: string; label: string; desc: string }) => (
      <div key={item.key} className={s.toggleItem}>
        <div>
          <div className={s.toggleLabel}>{item.label}</div>
          <div className={s.toggleDesc}>{item.desc}</div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={!!local[item.key]}
          aria-label={item.label}
          className={`${s.toggleSwitch} ${local[item.key] ? s.toggleSwitchOn : s.toggleSwitchOff}`}
          onClick={() => setLocal({...local, [item.key]: !local[item.key]})}
        >
          <div className={`${s.toggleKnob} ${local[item.key] ? s.toggleKnobOn : s.toggleKnobOff}`} />
        </button>
      </div>
    ))}
    <div className={s.toggleItem}>
      <div>
        <div className={s.toggleLabel}>Rebuild Search Index</div>
        <div className={s.toggleDesc}>
          Re-embed every one of your documents from its stored file. Use this when documents
          show as indexed but chat can't find them.
        </div>
      </div>
      <button className={s.reindexBtn} onClick={handleReindex} disabled={isReindexing}>
        {isReindexing ? (
          <><Icon name="Loader2" size={14} className={s.spin} /> Rebuilding…</>
        ) : (
          <><Icon name="RefreshCw" size={14} /> Rebuild</>
        )}
      </button>
    </div>
  </div>
  );
};
