import { useId } from 'react';
import type { RagSettings } from '../../../types';

interface RetrievalTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  s: Record<string, string>;
}

export const RetrievalTab = ({ local, setLocal, s }: RetrievalTabProps) => {
  const id = useId();
  return (
  <div className={s.settingsGrid}>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-vector-db`}>Vector Database</label>
      <select id={`${id}-vector-db`} className={s.select} value={local.vectorDb} onChange={e => setLocal({...local, vectorDb: e.target.value})}>
        <option value="chroma">ChromaDB (Default - Local)</option>
        <option value="pinecone">Pinecone (Cloud)</option>
        <option value="weaviate">Weaviate</option>
        <option value="qdrant">Qdrant</option>
        <option value="milvus">Milvus</option>
      </select>
    </div>
    <div className={s.settingGroup}>
      <label className={s.settingLabel} htmlFor={`${id}-index-name`}>Index Name</label>
      <input id={`${id}-index-name`} type="text" className={s.modalInput} value={local.indexName} onChange={e => setLocal({...local, indexName: e.target.value})} />
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-top-k`}>Top K Results</label>
        <span className={`${s.sliderValue} mono`}>{local.topK}</span>
      </div>
      <input id={`${id}-top-k`} type="range" min="1" max="25" value={local.topK} onChange={e => setLocal({...local, topK: parseInt(e.target.value)})} />
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-similarity-threshold`}>Similarity Threshold</label>
        <span className={`${s.sliderValue} mono`}>{local.similarityThreshold.toFixed(2)}</span>
      </div>
      <input id={`${id}-similarity-threshold`} type="range" min="0.05" max="0.95" step="0.05" value={local.similarityThreshold} onChange={e => setLocal({...local, similarityThreshold: parseFloat(e.target.value)})} />
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-chunk-size`}>Chunk Size (tokens)</label>
        <span className={`${s.sliderValue} mono`}>{local.chunkSize}</span>
      </div>
      <input id={`${id}-chunk-size`} type="range" min="256" max="2048" step="128" value={local.chunkSize} onChange={e => setLocal({...local, chunkSize: parseInt(e.target.value)})} />
    </div>
    <div className={s.settingGroup}>
      <div className={s.sliderHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-chunk-overlap`}>Chunk Overlap</label>
        <span className={`${s.sliderValue} mono`}>{local.chunkOverlap}</span>
      </div>
      <input id={`${id}-chunk-overlap`} type="range" min="0" max="512" step="32" value={local.chunkOverlap} onChange={e => setLocal({...local, chunkOverlap: parseInt(e.target.value)})} />
    </div>
  </div>
  );
};
