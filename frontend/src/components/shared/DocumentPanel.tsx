import React, { useState, useRef } from 'react';
import { Icon } from './Icon';
import { formatFileSize, generateId } from '../../utils';
import { api } from '../../api';
import type { UploadedDocument } from '../../types';
import s from './DocumentPanel.module.css';
import logger from '../../utils/logger';

interface DocumentPanelProps {
  documents: UploadedDocument[];
  onUpload: (doc: UploadedDocument) => void;
  onRemove: (id: string) => void;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  onUpdateDoc?: (id: string, updates: Partial<UploadedDocument>) => void;
  isAuthenticated: boolean;
  onAuthRequired?: () => void;
}

/** How long a successfully indexed upload stays visible before it vanishes —
    the file lives in the Knowledge Base; the chip is just the confirmation. */
const SUCCESS_LINGER_MS = 2500;

export const DocumentPanel = ({ documents, onUpload, onRemove, inputRef, onUpdateDoc, isAuthenticated, onAuthRequired }: DocumentPanelProps) => {
  const localFileRef = useRef<HTMLInputElement>(null);
  const fileRef = inputRef || localFileRef;
  const [dragOver, setDragOver] = useState(false);
  const [_uploading, setUploading] = useState<Record<string, boolean>>({});

  const handleFiles = async (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      const tempId = generateId();

      onUpload({
        id: tempId,
        name: file.name,
        size: file.size,
        type: file.type,
        uploadedAt: new Date(),
        status: 'uploading',
        file: file,
      });

      setUploading(prev => ({ ...prev, [tempId]: true }));

      try {
        const result = await api.uploadDocument(file, {
          filename: file.name,
          content_type: file.type,
        });

        const docId = (result.document_id as string) || result.id || tempId;
        if (onUpdateDoc) {
          const meta = result.metadata as Record<string, string> | undefined;
          onUpdateDoc(tempId, {
            id: docId,
            serverId: docId,
            status: result.status === 'failed' ? 'error' : 'indexed',
            chunks: (result.chunk_count as number) || 0,
            error: result.status === 'failed' ? (meta?.error || 'Failed to index document') : undefined,
            indexed_at: (result.indexed_at as string) || new Date().toISOString(),
          });
        }
        // A successful upload confirms itself briefly, then the chip goes —
        // the file lives in the Knowledge Base, not in a sidebar list.
        // Failures stay visible until dismissed.
        if (result.status !== 'failed') {
          setTimeout(() => onRemove(docId), SUCCESS_LINGER_MS);
        }
        // Keep the header count and the Knowledge Base list in sync with the
        // upload — neither should need a manual refresh to notice a new file.
        import('../../stores/settingsStore').then(({ useSettingsStore }) =>
          useSettingsStore.getState().refreshSystemStats());
        import('../../stores/ragDocsStore').then(({ useRagDocsStore }) => {
          if (useRagDocsStore.getState()._initialized) {
            useRagDocsStore.getState().loadRagDocuments();
          }
        });
      } catch (error: unknown) {
        logger.error('Upload error:', error);
        if (onUpdateDoc) {
          // An abort means the request timed out client-side — the server may
          // well still finish indexing, so say that instead of a raw AbortError.
          const timedOut = error instanceof DOMException && error.name === 'AbortError';
          onUpdateDoc(tempId, {
            status: 'error',
            error: timedOut
              ? 'Upload timed out — the file may still be indexing. Check the Knowledge Base in a minute.'
              : error instanceof Error ? error.message : String(error),
          });
        }
      }

      setUploading(prev => {
        const next = { ...prev };
        delete next[tempId];
        return next;
      });
    }
  };

  return (
    <div className={s.docPanel}>
      <div
        className={`${s.dropZone} ${dragOver ? s.dropZoneActive : ''} ${!isAuthenticated ? s.dropZoneDisabled : ''}`}
        onDragOver={e => { e.preventDefault(); if (isAuthenticated) setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); if (isAuthenticated) handleFiles(e.dataTransfer.files); else onAuthRequired?.(); }}
        onClick={() => isAuthenticated ? fileRef.current?.click() : onAuthRequired?.()}
      >
        <input aria-label="Upload documents" ref={fileRef} type="file" multiple accept=".pdf,.doc,.docx,.xlsx,.xls,.pptx,.odt,.txt,.md,.rtf,.csv,.tsv,.html,.htm,.json,.eml,.msg" className={s.hiddenInput} onChange={e => handleFiles(e.target.files)} />
        {!isAuthenticated && <Icon name="Lock" size={14} className={s.lockBadge} />}
        <Icon name={isAuthenticated ? "Upload" : "Lock"} size={22} className={s.iconMuted} />
        <span className={s.dropText}>{isAuthenticated ? 'Drop files or click to upload' : 'Register to upload documents'}</span>
        {isAuthenticated && <span className={s.dropHint}>PDF, Word, Excel, PowerPoint, CSV, email &amp; more</span>}
      </div>

      {documents.length > 0 && (
        <div className={s.docList}>
          {documents.map(doc => (
            <div key={doc.id} className={s.docItem}>
              {doc.status === 'uploading' ? (
                <Icon name="Loader" size={16} className={s.iconUploading} />
              ) : doc.status === 'error' ? (
                <Icon name="AlertCircle" size={16} className={s.iconError} />
              ) : doc.status === 'indexed' ? (
                <Icon name="CheckCircle" size={16} className={s.iconSuccess} />
              ) : (
                <Icon name="FileText" size={16} className={s.iconFile} />
              )}
              <div className={s.docInfo}>
                <span className={s.docName}>{doc.name}</span>
                <span className={s.docMeta}>
                  {doc.status === 'uploading' ? 'Uploading...' :
                   doc.status === 'error' ? (doc.error || 'Upload failed') :
                   doc.status === 'indexed' ? `Upload successful · ${doc.chunks || 0} chunks` :
                   formatFileSize(doc.size)}
                </span>
              </div>
              {/* Only failures are dismissible — successes vanish on their own,
                  and dismissing never deletes anything from the Knowledge Base. */}
              {doc.status === 'error' && (
                <button className={s.docRemove} onClick={() => onRemove(doc.id)} aria-label="Dismiss">
                  <Icon name="X" size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
