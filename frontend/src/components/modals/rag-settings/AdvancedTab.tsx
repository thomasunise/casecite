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
      { key: 'enableReranking', label: 'Enable Reranking', desc: 'Use cross-encoder to rerank retrieved results' },
      { key: 'hybridSearch', label: 'Hybrid Search', desc: 'Combine semantic and keyword search (BM25)' },
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
          Re-embed every document from its stored file. Use this when documents show as
          indexed but chat can't find them (admin only).
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
