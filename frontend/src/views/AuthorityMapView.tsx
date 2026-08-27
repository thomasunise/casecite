import { useRef, useState } from 'react';
import { useAuthorityMapStore } from '../stores/authorityMapStore';
import { useResearch } from '../contexts/ResearchContext';
import { Icon, AnnotatedDocument, ContractFilePicker, PdfDocumentViewer } from '../components';
import type { AuthorityMapping } from '../api/types';
import { mappingToCitation } from '../utils';
import s from './AuthorityMapView.module.css';

function AuthorityMapView() {
  const {
    docText, docName, fileUrl, fileType, jurisdiction,
    filePickerOpen, fileLoading, status, error, result, annotations,
    setJurisdiction,
    openFilePicker, closeFilePicker, loadUploadedFile, loadIndexedDocument, clearDocument, run,
  } = useAuthorityMapStore();
  const { setSelectedCitation } = useResearch();
  const verify = (m: AuthorityMapping, i = 0) => setSelectedCitation(mappingToCitation(m, i));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [viewMode, setViewMode] = useState<'document' | 'text'>('document');

  const running = status === 'running';
  const hasDoc = !!docText.trim();
  const isPdf = fileType === 'pdf' && !!fileUrl;
  const effectiveMode = isPdf ? viewMode : 'text';

  return (
    <div className={s.view}>
      {/* Toolbar */}
      <div className={s.toolbar}>
        <input
          aria-label="Upload a document"
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt,.rtf"
          className={s.hiddenInput}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) loadUploadedFile(f); e.target.value = ''; }}
        />
        <button className={s.toolBtn} onClick={() => fileInputRef.current?.click()} disabled={fileLoading || running}>
          <Icon name="Upload" size={14} /> Upload file
        </button>
        <button className={s.toolBtn} onClick={openFilePicker} disabled={fileLoading || running}>
          <Icon name="FolderSearch" size={14} /> Select file
        </button>

        {hasDoc && (
          <span className={s.docName} title={docName}>
            <Icon name="FileText" size={14} /> {docName || 'Document'}
            <button className={s.clearBtn} onClick={clearDocument} aria-label="Clear"><Icon name="X" size={12} /></button>
          </span>
        )}

        {isPdf && (
          <span className={s.toggle}>
            <button className={`${s.toggleBtn} ${effectiveMode === 'document' ? s.toggleActive : ''}`} onClick={() => setViewMode('document')}>Document</button>
            <button className={`${s.toggleBtn} ${effectiveMode === 'text' ? s.toggleActive : ''}`} onClick={() => setViewMode('text')}>Text + highlights</button>
          </span>
        )}

        <span className={s.spacer} />

        <input
          aria-label="Jurisdiction"
          className={s.jurisInput}
          placeholder="Jurisdiction (e.g. CA)"
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          disabled={running}
        />
        <button className={s.runBtn} onClick={run} disabled={running || !hasDoc}>
          {running ? <><Icon name="Loader2" size={14} className={s.spin} /> Mapping…</> : <><Icon name="ScanSearch" size={14} /> Map citations</>}
        </button>
      </div>

      {/* Status strip */}
      {running && (
        <div className={s.statusStrip}>
          <Icon name="Loader2" size={14} className={s.spin} />
          Reading the filing, retrieving authorities, and verifying each quote…
        </div>
      )}
      {status === 'error' && error && (
        <div className={`${s.statusStrip} ${s.statusError}`}><Icon name="AlertCircle" size={14} /> {error}</div>
      )}
      {result && (
        <div className={s.statusStrip}>
          {result.mappings.length === 0 ? (
            <span>No supporting authorities found.</span>
          ) : (
            <>
              <span className={s.statVerified}><Icon name="ShieldCheck" size={14} /> {result.summary.verified ?? 0} verified</span>
              <span>{result.summary.authorities ?? 0} authorities across {result.summary.propositions ?? 0} propositions — see Sources panel</span>
              {isPdf && effectiveMode === 'document' && <span className={s.statMuted}>Switch to “Text + highlights” to see citations inline</span>}
            </>
          )}
        </div>
      )}

      {/* Body: the document. Citations live in the right-hand Sources tab only. */}
      <div className={s.body}>
        <div className={s.docArea}>
          {!hasDoc ? (
            <div className={s.empty}>
              <Icon name="FileSearch" size={40} className={s.emptyIcon} />
              <h2 className={s.emptyTitle}>Case Citations</h2>
              <p className={s.emptyText}>Upload or select a filing — contract, brief, motion, or case file — and map it to supporting case law, verified against the real source.</p>
              <div className={s.emptyActions}>
                <button className={s.runBtn} onClick={() => fileInputRef.current?.click()}><Icon name="Upload" size={14} /> Upload file</button>
                <button className={s.toolBtn} onClick={openFilePicker}><Icon name="FolderSearch" size={14} /> Select file</button>
              </div>
            </div>
          ) : effectiveMode === 'document' ? (
            <PdfDocumentViewer fileUrl={fileUrl as string} />
          ) : (
            <div className={s.textScroll}>
              <AnnotatedDocument text={docText} annotations={annotations} onVerify={(m) => verify(m)} />
            </div>
          )}
        </div>
      </div>

      <ContractFilePicker
        isOpen={filePickerOpen}
        onClose={closeFilePicker}
        onSelect={(docs) => {
          // Authority mapping runs on ONE filing — the first selection wins.
          const doc = docs[0];
          if (doc) loadIndexedDocument(doc.id, { name: doc.name, filename: doc.name });
        }}
        loading={fileLoading}
      />
    </div>
  );
}

export default AuthorityMapView;
