import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useContractsStore } from '../stores/contractsStore';
import { useRagDocsStore } from '../stores/ragDocsStore';
import { useUIStore } from '../stores/uiStore';
import {
  Icon, ContractAnalysisMessage, ContractCitedAnswer, ContractTextViewer,
  RedlineSummary, ComparisonCard, ComparisonSplitView, DraftCard, ContractFilePicker,
  FloatingChatDock, AssistantAvatar, MessageMarkdown, AiNotice, CaseLawRemovedNotice,
} from '../components';
import { contractTypeLabel } from '../utils';
import s from './ContractsView.module.css';

function ContractsView() {
  const {
    selectedDocumentId, messages, sending, analyzing, progressMessage,
    analyses, analysesLoading, openingAnalysisId, exporting, uploadingContract,
    viewerOpen, contractText, contractFileUrl, contractTextLoading, redlineDecisions,
    redlineOverrides, setRedlineOverride, contractTextDirty, updateContractText, exportEditedContract,
    setSelectedDocumentId, init, sendMessage, openAnalysis, deleteAnalysis, exportAnalysis, uploadContract, clearConversation, exportConversation,
    toggleViewer, getViewerHighlights,
    setRedlineDecision, exportRedlineDocx, exportDraftDocx,
    getActiveRedlines, pendingEditJump, setActiveEditRef,
    comparisonView, comparisonJump, openComparisonView, closeComparisonView,
    openSplitDocs, compareOpenDocs, jumpToComparisonClause,
  } = useContractsStore();
  const navigate = useNavigate();
  const setRightPanelTab = useUIStore((st) => st.setRightPanelTab);
  const setRightSidebarCollapsed = useUIStore((st) => st.setRightSidebarCollapsed);
  const ragDocs = useRagDocsStore((st) => st.ragDocs);
  const ragInit = useRagDocsStore((st) => st.init);

  // Minimal local UI state only: composer text, past-analyses panel toggle,
  // compare-dropdown toggle, drag-over highlight, the file input ref, and
  // the auto-scroll anchor.
  const [input, setInput] = useState('');
  // Two gestures: Ask = conversation (questions & reviews, auto-routed);
  // Redline = markup mode — an act on the document, so it gets its own chip.
  const [composerMode, setComposerMode] = useState<'ask' | 'redline'>('ask');
  const [composerCollapsed, setComposerCollapsed] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const [citationJump, setCitationJump] = useState<
    { quotes: string[]; index: number; seq: number } | null
  >(null);
  const [showPast, setShowPast] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const lastMsgRef = useRef<HTMLDivElement | null>(null);
  const docCardRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { init(); ragInit(); }, [init, ragInit]);
  useEffect(() => {
    if (messages.length > 0) setChatOpen(true);
    // Land at the TOP of the newest message so long answers read from the start.
    lastMsgRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [messages.length, sending, analyzing]);

  const indexedDocs = ragDocs.filter((d) => d.status === 'indexed');
  const selectedDoc = indexedDocs.find((d) => d.id === selectedDocumentId);
  const activeRedlines = getActiveRedlines();
  const activeDecisions: Record<string, 'accepted' | 'rejected'> = {};
  const activeOverrides: Record<string, string> = {};
  if (activeRedlines) {
    for (const edit of activeRedlines.edits) {
      const key = `${activeRedlines.analysisId}:${edit.ref}`;
      const decision = redlineDecisions[key];
      if (decision) activeDecisions[edit.ref] = decision;
      const override = redlineOverrides[key];
      if (override) activeOverrides[edit.ref] = override;
    }
  }
  const busy = sending || analyzing;
  const openDocsCount = comparisonView?.docs.length ?? 0;
  const composerReady = !!selectedDocumentId;
  // Redline mode may send empty — "Redline this contract" is the instruction.
  const canSend = composerReady && !busy && (!!input.trim() || composerMode === 'redline');

  const handleSend = () => {
    const text = input.trim();
    if (!composerReady || busy) return;
    if (composerMode === 'redline') {
      setInput('');
      // Empty Enter = a plain redline; the whose-side clarify question (or
      // the playbook/practice profile) supplies the posture.
      sendMessage(text || 'Redline this contract.', 'redline');
      return;
    }
    if (!text) return;
    // With documents open side by side, saying "compare ..." IS the command —
    // the whole message rides along as the comparison's focus instructions.
    if (openDocsCount >= 2 && /\b(compare|comparison|differences?|diff)\b/i.test(text)) {
      setInput('');
      compareOpenDocs(text);
      return;
    }
    setInput('');
    // Ask: the message routes itself (questions, reviews, drafts — drafts
    // open in the Drafting tab).
    sendMessage(text);
  };

  const handleSelectionAction = (action: string, sel: string) => {
    const clause = sel.length > 1500 ? sel.slice(0, 1500) + '…' : sel;
    if (action === 'explain') {
      sendMessage(`Explain this clause and any risks it creates:
"${clause}"`);
    } else if (action === 'redline') {
      sendMessage(`Propose replacement language for this clause and explain each change:
"${clause}"`);
    } else if (action === 'rewrite') {
      sendMessage(`Rewrite this clause in plainer terms that favor my side, and explain what changed:
"${clause}"`);
    } else {
      setInput(`About this clause: "${clause.slice(0, 160)}${clause.length > 160 ? '…' : ''}" — `);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadContract(file);
  };

  return (
    <div
      className={s.view}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false); }}
      onDrop={handleDrop}
    >
      {dragOver && (
        <div className={s.dropOverlay}>
          <Icon name="Upload" size={40} />
          <span>Drop a contract to upload &amp; index it</span>
        </div>
      )}
      {/* Toolbar: compact document selector + upload + past analyses toggle */}
      <div className={s.toolbar}>
        <button
          className={s.docSelect}
          onClick={() => setPickerOpen(true)}
          disabled={busy}
          aria-label="Contract document"
        >
          <Icon name="FolderSearch" size={14} className={s.docSelectIcon} />
          <span className={s.docSelectName}>
            {selectedDoc ? selectedDoc.filename : 'Select files…'}
          </span>
        </button>
        <button
          className={s.uploadBtn}
          onClick={() => fileRef.current?.click()}
          disabled={uploadingContract || busy}
        >
          {uploadingContract
            ? <Icon name="Loader2" size={13} className={s.spin} />
            : <Icon name="Upload" size={13} />}
          {uploadingContract ? 'Indexing…' : 'Upload'}
        </button>
        <input
          aria-label="Upload a contract"
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt,.rtf"
          className={s.hiddenInput}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadContract(file);
            e.target.value = '';
          }}
        />
        <button
          className={viewerOpen ? s.pastToggleActive : s.pastToggle}
          onClick={() => toggleViewer()}
          disabled={!selectedDocumentId}
        >
          <Icon name="PanelRight" size={13} />
          {viewerOpen ? 'Hide contract' : 'View contract'}
        </button>
        <span className={s.spacer} />
        {(analyses.length > 0 || analysesLoading) && (
          <button
            className={showPast ? s.pastToggleActive : s.pastToggle}
            onClick={() => setShowPast(!showPast)}
          >
            <Icon name="History" size={13} />
            Past analyses{analyses.length > 0 ? ` (${analyses.length})` : ''}
            <Icon name={showPast ? 'ChevronUp' : 'ChevronDown'} size={12} />
          </button>
        )}
      </div>

      {/* Collapsible past analyses panel — clicking a row injects it into the chat */}
      {showPast && (
        <div className={s.pastPanel}>
          {analysesLoading && analyses.length === 0 && (
            <p className={s.pastEmpty}>Loading…</p>
          )}
          {analyses.map((a) => (
            <div key={a.analysis_id} className={s.pastItem}>
            <button
              className={s.pastRow}
              onClick={() => { openAnalysis(a.analysis_id); setShowPast(false); }}
              disabled={openingAnalysisId != null}
            >
              {openingAnalysisId === a.analysis_id
                ? <Icon name="Loader2" size={14} className={s.spin} />
                : <Icon name="FileText" size={14} className={s.pastRowIcon} />}
              <span className={s.pastType}>{contractTypeLabel(a.contract_type)}</span>
              <span className={s.pastMeta}>
                {a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}
              </span>
              <span className={s.pastMeta}>{a.issues} issue{a.issues === 1 ? '' : 's'}</span>
              <span className={s.spacer} />
              <Icon name="ChevronRight" size={14} className={s.pastChevron} />
            </button>
            <button
              className={s.pastDelete}
              onClick={() => deleteAnalysis(a.analysis_id)}
              disabled={openingAnalysisId != null}
              aria-label="Delete this analysis"
              title="Delete this analysis"
            >
              <Icon name="Trash2" size={13} />
            </button>
            </div>
          ))}
        </div>
      )}

      {/* Main column: the contract itself up top, conversation beneath it */}
      <div className={s.messagesWrap}>
        {comparisonView && (
          <ComparisonSplitView
            docs={comparisonView.docs}
            comparisons={comparisonView.comparisons}
            loading={comparisonView.loading}
            jump={comparisonJump}
            onClose={closeComparisonView}
          />
        )}
        {!comparisonView && selectedDocumentId && viewerOpen && (
          <div ref={docCardRef}>
          <ContractTextViewer
            filename={selectedDoc?.filename || 'Contract'}
            text={contractText || ''}
            fileUrl={contractFileUrl}
            loading={contractTextLoading}
            highlights={citationJump ? citationJump.quotes : getViewerHighlights()}
            jumpToHighlight={citationJump ? { index: citationJump.index, seq: citationJump.seq } : null}
            jumpToEditRef={pendingEditJump}
            onActiveEditChange={setActiveEditRef}
            onClose={() => toggleViewer()}
            onSelectionAction={handleSelectionAction}
            redlines={activeRedlines?.edits}
            redlineDecisions={activeDecisions}
            onRedlineDecision={(ref, decision) =>
              activeRedlines && setRedlineDecision(activeRedlines.analysisId, ref, decision)}
            proposedOverrides={activeOverrides}
            onProposedEdit={(ref, newText) =>
              activeRedlines && setRedlineOverride(activeRedlines.analysisId, ref, newText)}
            onTextEdit={updateContractText}
            textDirty={contractTextDirty}
            onExportEditedCopy={() => exportEditedContract(selectedDoc?.filename || 'contract')}
            onExportRedlines={() =>
              activeRedlines && exportRedlineDocx(activeRedlines.analysisId)}
            exportingRedlines={exporting}
          />
          </div>
        )}
        {!selectedDocumentId && (
          <div className={s.emptyState}>
            <Icon name="FileText" size={48} className={s.emptyStateIcon} />
            <h3 className={s.emptyTitle}>Contracts</h3>
            <p className={s.emptyText}>
              Pick a file and just say what you need — a full review from your side
              of the table, a redline, a question about a clause, or a specific term
              to check. Every finding is grounded in quotes from the document.
            </p>
            <div className={s.emptyActions}>
              <button className={s.emptySelectBtn} onClick={() => setPickerOpen(true)}>
                <Icon name="FolderSearch" size={15} />
                Select a file
              </button>
              <button
                className={s.emptyUploadBtn}
                onClick={() => fileRef.current?.click()}
                disabled={uploadingContract}
              >
                <Icon name="Upload" size={14} />
                {uploadingContract ? 'Indexing…' : 'Upload new'}
              </button>
              <button
                className={s.emptyUploadBtn}
                onClick={() => navigate('/drafting')}
              >
                <Icon name="PenLine" size={14} />
                Draft a document
              </button>
            </div>
            <p className={s.emptyHint}>…or drop a file anywhere on this page</p>
          </div>
        )}
      </div>

      {/* Floating conversation overlay — the contract stays the page */}
      {(messages.length > 0 || busy) && (
        <FloatingChatDock
          open={chatOpen}
          low={composerCollapsed}
          busy={busy}
          count={messages.length}
          onMinimize={() => setChatOpen(false)}
          onExpand={() => setChatOpen(true)}
          onClear={clearConversation}
          onExport={(format) => exportConversation(format, selectedDoc?.filename)}
          exporting={exporting}
          className={s.dockOffsets}
        >
          {messages.map((msg, msgIndex) => (
            <div
              key={msg.id}
              ref={msgIndex === messages.length - 1 ? lastMsgRef : undefined}
              className={msg.role === 'user' ? s.messageRowUser : s.messageRowAssistant}
            >
              {msg.role === 'assistant' && (
                <div className={s.assistantAvatar}><AssistantAvatar /></div>
              )}
              <div className={
                msg.role === 'user' ? s.userBubble
                  : msg.kind === 'answer' || msg.kind === 'text' ? s.assistantBubble
                  : s.analysisBubble
              }>
                {msg.role === 'user' && (
                  <div className={s.userMessageContent}>{msg.text}</div>
                )}
                {msg.role === 'assistant' && msg.kind === 'analysis' && msg.analysis && (
                  <ContractAnalysisMessage
                    analysis={msg.analysis}
                    exporting={exporting}
                    onExport={exportAnalysis}
                  />
                )}
                {msg.role === 'assistant' && msg.kind === 'redlines' && msg.redlines && msg.analysisId && (
                  <RedlineSummary
                    edits={msg.redlines}
                    basis={msg.text}
                    exporting={exporting}
                    onExport={() => exportRedlineDocx(msg.analysisId!)}
                    onViewInDocument={() => {
                      setRightPanelTab('sources');
                      setRightSidebarCollapsed(false);
                      docCardRef.current?.scrollIntoView({ behavior: 'smooth' });
                    }}
                  />
                )}
                {msg.role === 'assistant' && msg.kind === 'comparison' && msg.comparison && (
                  <ComparisonCard
                    comparison={msg.comparison}
                    onOpenSplitView={(clauseIndex) => {
                      if (clauseIndex != null) {
                        jumpToComparisonClause(msg.comparison!, clauseIndex);
                      } else {
                        openComparisonView([msg.comparison!]);
                      }
                      setChatOpen(false);
                    }}
                  />
                )}
                {msg.role === 'assistant' && msg.kind === 'comparison_set' && msg.comparisonSet && (
                  <div className={s.comparisonSetStack}>
                    {msg.comparisonSet.comparisons.map((comparison, ci) => (
                      <ComparisonCard
                        key={ci}
                        comparison={comparison}
                        onOpenSplitView={(clauseIndex) => {
                          if (clauseIndex != null) {
                            jumpToComparisonClause(comparison, clauseIndex);
                          } else {
                            openComparisonView(msg.comparisonSet!.comparisons);
                          }
                          setChatOpen(false);
                        }}
                      />
                    ))}
                  </div>
                )}
                {msg.role === 'assistant' && msg.kind === 'draft' && msg.draft && (
                  <DraftCard draft={msg.draft} exporting={exporting} onDownload={exportDraftDocx} />
                )}
                {msg.role === 'assistant' && msg.kind === 'answer' && (
                  <ContractCitedAnswer
                    text={msg.text || ''}
                    citations={msg.citations || []}
                    onCitationJump={(index) => msg.citations && setCitationJump((prev) => ({
                      quotes: msg.citations!.map((c) => c.quote),
                      index,
                      seq: (prev?.seq || 0) + 1,
                    }))}
                  />
                )}
                {msg.role === 'assistant' && msg.kind === 'answer' && (
                  <CaseLawRemovedNotice removed={msg.caseLawRemoved} />
                )}
                {msg.role === 'assistant' && msg.kind === 'text' && (
                  <MessageMarkdown text={msg.text || ''} />
                )}
                {/* Analyses, redlines, drafts and cited answers carry their own
                    notice inside the card; the rest get it here. */}
                {msg.role === 'assistant'
                  && (msg.kind === 'text' || msg.kind === 'comparison' || msg.kind === 'comparison_set')
                  && <AiNotice />}
                {msg.role === 'assistant' && msg.kind === 'clarify' && (
                  <div>
                    <MessageMarkdown text={msg.text || ''} />
                    <div className={s.clarifyOptions}>
                      {(msg.options || []).map((option) => (
                        <button
                          key={option}
                          className={s.clarifyChip}
                          disabled={busy}
                          onClick={() => sendMessage(`${msg.originalMessage || 'Redline this contract'}. ${option}.`)}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {busy && (
          <div className={s.messageRowAssistant}>
            <div className={s.assistantAvatar}><AssistantAvatar /></div>
            <div className={s.processingBubble}>
              <div className={s.processingContent}>
                <Icon name="Loader2" size={16} className={s.spin} />
                <span>{analyzing ? progressMessage : 'Reading the contract…'}</span>
              </div>
              <div className={s.progressBar}>
                <div className={s.progressFill} />
              </div>
            </div>
          </div>
          )}
        </FloatingChatDock>
      )}

      {/* Full-document view: the whole composer collapses to a floating pill */}
      {composerCollapsed && (
        <button className={s.composerToggle} onClick={() => setComposerCollapsed(false)}>
          <Icon name="MessageSquarePlus" size={13} /> Composer
        </button>
      )}

      {/* Two gestures: Ask (conversation) / Redline (markup) */}
      {!composerCollapsed && composerReady && (
        <div className={s.actionBar}>
          <button
            className={composerMode === 'ask' ? s.actionChipActive : s.actionChip}
            onClick={() => setComposerMode('ask')}
          >
            <Icon name="MessageSquare" size={13} /> Ask
          </button>
          <button
            className={composerMode === 'redline' ? s.actionChipActive : s.actionChip}
            onClick={() => setComposerMode('redline')}
          >
            <Icon name="FilePen" size={13} /> Redline
          </button>
        </div>
      )}

      {/* Floating composer */}
      {!composerCollapsed && (
      <div className={s.inputSection}>
        <div className={s.inputWrap}>
          <input
            aria-label="Ask about the selected files"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSend(); }}
            placeholder={!selectedDocumentId
              ? 'Select a file above to start…'
              : composerMode === 'redline'
                ? 'Your redlining instructions — who you represent, what to push for (or just press Enter)…'
              : openDocsCount >= 2 && (comparisonView?.comparisons.length ?? 0) === 0
                ? `Say "compare these ${openDocsCount} files" — add what to focus on, or ask anything…`
                : 'Ask anything or request a review — just say what you need…'}
            className={s.input}
            disabled={!composerReady || busy}
          />
          <button
            className={`${s.sendBtn} ${!canSend ? s.sendBtnDisabled : ''}`}
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Send"
          >
            <Icon name="Send" size={18} />
          </button>
        </div>
        <div className={s.inputHints}>
          {composerReady ? (
            <span>Press <kbd className={s.kbd}>Enter</kbd> to send</span>
          ) : (
            <span>Select a file to get started — drafting lives in its own tab</span>
          )}
          <button
            className={s.composerCollapseBtn}
            onClick={() => setComposerCollapsed(true)}
            title="Hide the composer for a full document view"
          >
            <Icon name="ChevronsDown" size={12} /> Hide
          </button>
        </div>
      </div>
      )}

      <ContractFilePicker
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(docs) => {
          setPickerOpen(false);
          if (docs.length === 1) {
            closeComparisonView();
            setSelectedDocumentId(docs[0].id);
          } else if (docs.length > 1) {
            // Multi-select: all of them open side by side; first is primary.
            openSplitDocs(docs);
          }
        }}
      />
    </div>
  );
}

export default ContractsView;
