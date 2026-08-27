import { useEffect, useId, useRef, useState } from 'react';
import { useDraftingStore, WORDS_PER_PAGE } from '../stores/draftingStore';
import {
  Icon, ContractTextViewer, ContractFilePicker, FloatingChatDock, AssistantAvatar, MessageMarkdown, AiNotice,
} from '../components';
import s from './DraftingView.module.css';

/**
 * Drafting — its own workspace, drafting-first. The canvas IS the home
 * screen: attach reference documents up top, describe what you need below,
 * and the drafted document becomes the page with the full highlight /
 * rewrite / edit / export toolkit. The composer is the revision loop.
 *
 * Long documents (a target length is set) go plan-first: the plan is laid
 * out on the canvas for review, and only an approved plan is drafted —
 * every section in its own context window, then reconciled.
 */
function DraftingView() {
  const id = useId();
  const {
    messages, sending, progressMessage, exporting,
    draftWorkspace, draftReferences,
    targetPages, setTargetPages,
    draftPlan, updatePlanField, updatePlanSection, removePlanSection, addPlanSection,
    discardPlan, generateFromPlan,
    updateDraftText, closeDraftWorkspace,
    attachDraftReferences, removeDraftReference,
    sendDraftMessage, exportDraftDocx, clearConversation, exportConversation,
  } = useDraftingStore();

  const [input, setInput] = useState('');
  const [chatOpen, setChatOpen] = useState(true);
  const [composerCollapsed, setComposerCollapsed] = useState(false);
  const [refPickerOpen, setRefPickerOpen] = useState(false);
  const [planExtrasOpen, setPlanExtrasOpen] = useState(false);
  const lastMsgRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (messages.length > 0) setChatOpen(true);
    lastMsgRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [messages.length, sending]);
  // A freshly generated draft (or a plan to review) is the point — minimize the conversation.
  useEffect(() => {
    if ((draftWorkspace && !draftWorkspace.dirty) || draftPlan) setChatOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftWorkspace?.text, draftWorkspace?.dirty, draftPlan]);

  const canSend = !sending && !!input.trim();
  const handleSend = () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    sendDraftMessage(text, 'draft');
  };

  // Selection actions on the draft: rewrites revise in place; explain answers
  // over the draft; ask prefills the composer.
  const handleSelectionAction = (action: string, sel: string) => {
    const clause = sel.length > 1500 ? sel.slice(0, 1500) + '…' : sel;
    if (action === 'explain') {
      sendDraftMessage(`Explain this clause of the draft and any risks it creates:\n"${clause}"`, undefined);
    } else if (action === 'redline' || action === 'rewrite') {
      sendDraftMessage(`Rewrite this clause — stronger, clearer language; keep every other part of the draft unchanged:\n"${clause}"`, 'draft');
    } else {
      setInput(`About this clause: "${clause.slice(0, 160)}${clause.length > 160 ? '…' : ''}" — `);
    }
  };

  const planPages = draftPlan
    ? Math.max(1, Math.round(draftPlan.sections.reduce((sum, sec) => sum + (Number(sec.target_words) || 0), 0) / WORDS_PER_PAGE))
    : 0;

  return (
    <div className={s.view}>
      <div className={s.scrollArea}>
        {/* Reference documents bar — the draft's source material */}
        <div className={s.refCard}>
          <span className={s.refLabel}>Reference documents</span>
          {draftReferences.map((ref) => (
            <div key={ref.id} className={s.refChip}>
              <Icon name="FileText" size={13} />
              <span className={s.refName}>{ref.name}</span>
              <button
                className={s.refClear}
                onClick={() => removeDraftReference(ref.id)}
                aria-label={`Remove ${ref.name}`}
              >
                <Icon name="X" size={12} />
              </button>
            </div>
          ))}
          <button
            className={s.attachBtn}
            onClick={() => setRefPickerOpen(true)}
            disabled={draftReferences.length >= 4}
            title="Pick documents from your Knowledge Base the draft should be based on — e.g. your service agreement"
          >
            <Icon name="Plus" size={13} />
            Attach reference
          </button>
        </div>

        {/* The document — the plan under review — or the canvas awaiting one */}
        {draftWorkspace ? (
          <>
            <ContractTextViewer
              filename={draftWorkspace.title || 'Draft'}
              text={draftWorkspace.text}
              loading={false}
              highlights={[]}
              onClose={closeDraftWorkspace}
              onSelectionAction={handleSelectionAction}
              onTextEdit={updateDraftText}
              textDirty={draftWorkspace.dirty}
              onExportEditedCopy={exportDraftDocx}
            />
            <AiNotice className={s.draftNotice} />
          </>
        ) : draftPlan && !sending ? (
          <div className={s.planCard} data-testid="draft-plan">
            <div className={s.planHeader}>
              <div className={s.planHeaderText}>
                <span className={s.refLabel}>Section plan — review before drafting</span>
                <input
                  aria-label="Document title"
                  className={s.planTitleInput}
                  value={draftPlan.title}
                  onChange={(e) => updatePlanField('title', e.target.value)}
                />
                <div className={s.planMeta}>
                  {draftPlan.document_type && <span>{draftPlan.document_type}</span>}
                  <span>{draftPlan.sections.length} sections</span>
                  <span>~{planPages} pages</span>
                  {draftPlan.references_mode === 'full' && <span>every section reads the full references</span>}
                  {draftPlan.references_mode === 'excerpts' && <span>references sent as focused excerpts per section</span>}
                </div>
              </div>
            </div>

            <ol className={s.planSections}>
              {draftPlan.sections.map((sec, i) => (
                <li key={`${sec.number}-${i}`} className={s.planSection}>
                  <div className={s.planSectionHead}>
                    <span className={s.planNum}>{sec.number}.</span>
                    <input
                      aria-label={`Section ${sec.number} title`}
                      className={s.planInput}
                      value={sec.title}
                      onChange={(e) => updatePlanSection(i, { title: e.target.value })}
                      placeholder="Section title"
                    />
                    <label className={s.planWords}>
                      <input
                        aria-label={`Section ${sec.number} target words`}
                        type="number"
                        min={100}
                        max={2500}
                        step={50}
                        value={sec.target_words}
                        onChange={(e) => updatePlanSection(i, { target_words: Number(e.target.value) || 0 })}
                      />
                      words
                    </label>
                    <button
                      className={s.planIconBtn}
                      onClick={() => addPlanSection(i)}
                      title="Add a section after this one"
                      aria-label={`Add section after ${sec.number}`}
                    >
                      <Icon name="Plus" size={13} />
                    </button>
                    <button
                      className={s.planIconBtn}
                      onClick={() => removePlanSection(i)}
                      disabled={draftPlan.sections.length <= 1}
                      title="Remove this section"
                      aria-label={`Remove section ${sec.number}`}
                    >
                      <Icon name="X" size={13} />
                    </button>
                  </div>
                  <textarea
                    aria-label={`Section ${sec.number} brief`}
                    className={s.planTextarea}
                    value={sec.brief}
                    onChange={(e) => updatePlanSection(i, { brief: e.target.value })}
                    placeholder="What this section must cover — clauses, positions, cross-references"
                    rows={2}
                  />
                  <textarea
                    aria-label={`Section ${sec.number} exclusions`}
                    className={`${s.planTextarea} ${s.planTextareaMuted}`}
                    value={sec.exclude}
                    onChange={(e) => updatePlanSection(i, { exclude: e.target.value })}
                    placeholder="Leaves to other sections (so nothing is drafted twice)"
                    rows={1}
                  />
                </li>
              ))}
            </ol>

            <button className={s.planExtrasToggle} onClick={() => setPlanExtrasOpen((v) => !v)}>
              <Icon name={planExtrasOpen ? 'ChevronDown' : 'ChevronRight'} size={13} />
              Shared definitions &amp; style guide
            </button>
            {planExtrasOpen && (
              <div className={s.planExtras}>
                <label className={s.planExtraLabel} htmlFor={`${id}-definitions`}>
                  Definitions every section must use
                  <textarea
                    id={`${id}-definitions`}
                    className={s.planTextarea}
                    value={draftPlan.definitions}
                    onChange={(e) => updatePlanField('definitions', e.target.value)}
                    rows={5}
                  />
                </label>
                <label className={s.planExtraLabel} htmlFor={`${id}-style-guide`}>
                  Style guide
                  <textarea
                    id={`${id}-style-guide`}
                    className={s.planTextarea}
                    value={draftPlan.style_guide}
                    onChange={(e) => updatePlanField('style_guide', e.target.value)}
                    rows={3}
                  />
                </label>
              </div>
            )}

            <div className={s.planFooter}>
              <button className={s.planDiscard} onClick={discardPlan}>Discard plan</button>
              <button className={s.planGenerate} onClick={generateFromPlan}>
                <Icon name="PenLine" size={15} />
                Draft {draftPlan.sections.length} sections (~{planPages} pages)
              </button>
            </div>
          </div>
        ) : (
          <div className={s.canvas}>
            {sending ? (
              <div className={s.canvasBody}>
                <Icon name="Loader2" size={28} className={s.spin} />
                <h3 className={s.canvasTitle}>{progressMessage || 'Drafting…'}</h3>
                <p className={s.canvasText}>
                  The document will appear here — full text, ready to edit,
                  rewrite clause by clause, and export to Word.
                </p>
              </div>
            ) : (
              <div className={s.canvasBody}>
                <Icon name="PenLine" size={28} className={s.canvasIcon} />
                <h3 className={s.canvasTitle}>What are we drafting?</h3>
                <p className={s.canvasText}>
                  Describe it below — a contract, an amendment, a demand letter,
                  anything. Attach reference documents above to draft from them:
                  &ldquo;write me a demand letter based on this service agreement.&rdquo;
                </p>
                <p className={s.canvasText}>
                  For a long document, set a target length. You&rsquo;ll get a section
                  plan to review first; each section is then drafted with the full
                  reference documents in view and the whole is reconciled.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Conversation — same dock as every chat page */}
      {(messages.length > 0 || sending) && (
        <FloatingChatDock
          open={chatOpen}
          low={composerCollapsed}
          busy={sending}
          count={messages.length}
          onMinimize={() => setChatOpen(false)}
          onExpand={() => setChatOpen(true)}
          onClear={clearConversation}
          onExport={exportConversation}
          exporting={exporting}
          className={s.dockOffsets}
        >
          {messages.map((msg, i) => (
            <div
              key={msg.id}
              ref={i === messages.length - 1 ? lastMsgRef : undefined}
              className={msg.role === 'user' ? s.messageRowUser : s.messageRow}
            >
              {msg.role === 'assistant' && (
                <div className={s.assistantAvatar}><AssistantAvatar /></div>
              )}
              <div className={msg.role === 'user' ? s.userBubble : s.assistantBubble}>
                {msg.role === 'assistant'
                  ? <><MessageMarkdown text={msg.text} /><AiNotice /></>
                  : <div className={s.userText}>{msg.text}</div>}
              </div>
            </div>
          ))}
          {sending && (
            <div className={s.messageRow}>
              <div className={s.assistantAvatar}><AssistantAvatar /></div>
              <div className={s.processingBubble}>
                <Icon name="Loader2" size={16} className={s.spin} />
                <span>{progressMessage || 'Working…'}</span>
              </div>
            </div>
          )}
        </FloatingChatDock>
      )}

      {/* Collapsed-composer pill */}
      {composerCollapsed && (
        <button className={s.composerToggle} onClick={() => setComposerCollapsed(false)}>
          <Icon name="MessageSquarePlus" size={13} /> Composer
        </button>
      )}

      {/* Composer — one input, always drafting */}
      {!composerCollapsed && (
        <div className={s.inputSection}>
          <div className={s.inputWrap}>
            <input
              aria-label={draftWorkspace ? 'Steer the draft' : 'Describe what to draft'}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSend(); }}
              placeholder={draftWorkspace
                ? 'Steer the draft — "make the term 3 years", "add an arbitration clause"…'
                : 'Describe what to draft — type, parties, key terms, jurisdiction…'}
              className={s.input}
              disabled={sending}
            />
            {!draftWorkspace && (
              <label className={s.lengthControl} title="Set a target length for a long document — it will be planned section by section first. Leave blank for letters, amendments and other short drafts.">
                <span>Length</span>
                <input
                  aria-label="Target length in pages"
                  type="number"
                  min={1}
                  max={200}
                  placeholder="auto"
                  value={targetPages ?? ''}
                  onChange={(e) => setTargetPages(e.target.value === '' ? null : Number(e.target.value))}
                  className={s.lengthInput}
                  disabled={sending}
                />
                <span>pages</span>
              </label>
            )}
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
            <span>Press <kbd className={s.kbd}>Enter</kbd> to send</span>
            {!draftWorkspace && targetPages && (
              <span>· ~{targetPages} pages: plan first, then draft section by section</span>
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

      {/* Reference picker — the Knowledge Base, not the local disk */}
      <ContractFilePicker
        isOpen={refPickerOpen}
        onClose={() => setRefPickerOpen(false)}
        onSelect={(docs) => { setRefPickerOpen(false); attachDraftReferences(docs); }}
        subtitle="Pick up to 4 documents the draft should be based on"
        confirmLabel={(n) => n > 1 ? `Attach ${n} references` : 'Attach reference'}
        multiHint=" as drafting sources"
      />
    </div>
  );
}

export default DraftingView;
