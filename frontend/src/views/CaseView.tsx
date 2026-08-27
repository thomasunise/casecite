import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useCaseViewStore } from '../stores/caseViewStore';
import type { CaseMessage } from '../types';
import s from './CaseView.module.css';
// Shared tool-page shell: scrolling content + the app-wide floating composer.
import t from './ToolsView.module.css';
import { Icon, DocumentSelector, FloatingChatDock, AssistantAvatar, MessageMarkdown, AiNotice } from '../components';

// Static constants only (no components, no rendering functions).
// Composer placeholder ticker — starter hints rotate inside the input, same
// construction as Matter Strategy, instead of sitting above the composer as chips.
const CASE_ONLY_HINTS = [
  'Ask about this case…',
  'Key legal issues?',
  'How was this decided?',
  'What precedent does this set?',
] as const;
const WITH_DOCS_HINTS = [
  'Ask about this case + your documents…',
  'How does this apply to my case?',
  'Compare to my documents',
  'Similar cases in my database?',
] as const;
const HINT_ROTATE_MS = 3500;

function CaseView() {
  const {
    mainViewCase, caseLoading,
    closeCaseView,
    caseMessages,
    caseQueryInput, setCaseQueryInput,
    caseQueryLoading,
    caseQueryIncludeDocs, setCaseQueryIncludeDocs,
    caseDocFilter, setCaseDocFilter,
    showCaseDocSelector, setShowCaseDocSelector,
    queryCaseContext,
    initCaseFromRoute,
    clearCaseConversation, exportCaseConversation, exportingCaseConversation,
  } = useCaseViewStore();

  // On refresh or direct navigation nothing has loaded this case yet — the
  // route id is the source of truth, so let the store init from it.
  const { id: routeCaseId } = useParams<{ id: string }>();
  useEffect(() => {
    if (routeCaseId) initCaseFromRoute(routeCaseId);
  }, [routeCaseId, initCaseFromRoute]);

  const [detailsOpen, setDetailsOpen] = useState(true);
  // Local UI state only: the floating conversation dock and composer collapse.
  const [chatOpen, setChatOpen] = useState(true);
  const [composerCollapsed, setComposerCollapsed] = useState(false);

  // Rotate the composer's placeholder through the scope-appropriate hints.
  const composerHints = caseQueryIncludeDocs ? WITH_DOCS_HINTS : CASE_ONLY_HINTS;
  const [hintIndex, setHintIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setHintIndex((i) => (i + 1) % composerHints.length), HINT_ROTATE_MS);
    return () => clearInterval(timer);
  }, [composerHints.length]);
  const lastMsgRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (caseMessages.length > 0) setChatOpen(true);
    // Land at the TOP of the newest message so long answers read from the start.
    lastMsgRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [caseMessages.length]);

  return (
    <div className={s.caseViewArea}>
      {/* Compact Header */}
      <div className={s.caseHeader}>
        <button className={s.backBtn} onClick={closeCaseView} aria-label="Back to search">
          <Icon name="ArrowLeft" size={16} />
        </button>
        {mainViewCase && !mainViewCase.error && (
          <div className={s.caseHeaderInfo}>
            <h1 className={s.caseTitle}>{mainViewCase.case_name}</h1>
            <div className={s.caseMeta}>
              {mainViewCase.court && <span><Icon name="Building" size={12} /> {mainViewCase.court}</span>}
              {mainViewCase.date_filed && <span><Icon name="Calendar" size={12} /> {mainViewCase.date_filed}</span>}
              {(mainViewCase.times_cited ?? 0) > 0 && <span><Icon name="Quote" size={12} /> Cited {mainViewCase.times_cited}x</span>}
              {(mainViewCase.citations?.length ?? 0) > 0 && mainViewCase.citations?.map((cite: string | Record<string, unknown>, i: number) => (
                <span key={i} className={s.citeBadge}>
                  {typeof cite === 'string' ? cite : `${cite.volume || ''} ${cite.reporter || ''} ${cite.page || ''}`.trim() || 'Citation'}
                </span>
              ))}
            </div>
          </div>
        )}
        {mainViewCase && !mainViewCase.error && (mainViewCase.opinion_text || mainViewCase.syllabus) && (
          <button className={s.detailsToggle} onClick={() => setDetailsOpen(!detailsOpen)}>
            <Icon name={detailsOpen ? 'ChevronUp' : 'FileText'} size={14} />
            {detailsOpen ? 'Hide' : 'Opinion'}
          </button>
        )}
      </div>

      {/* Main content area: opinion + chat messages share this scrollable
          region; the composer floats over its bottom like every tool page. */}
      <div className={`${t.toolsView} ${s.caseBody}`}>
      <div className={`${t.resultsScroll} ${s.messagesWrap}`}>
        {caseLoading ? (
          <div className={s.loadingState}>
            <Icon name="Loader2" size={32} className={s.spinnerIcon} />
            <span>Loading case details...</span>
          </div>
        ) : mainViewCase?.error ? (
          <div className={s.errorState}>
            <Icon name="AlertCircle" size={24} />
            <span>{mainViewCase.error}</span>
          </div>
        ) : !mainViewCase ? (
          routeCaseId ? (
            <div className={s.loadingState}>
              <Icon name="Loader2" size={32} className={s.spinnerIcon} />
              <span>Loading case details...</span>
            </div>
          ) : (
            <div className={s.errorState}>
              <Icon name="FileSearch" size={24} />
              <span>No case selected — look one up with Case Lookup.</span>
            </div>
          )
        ) : (
          <>
            {/* Opinion / Syllabus — inline in the scroll area */}
            {detailsOpen && (
              <div className={s.opinionBlock}>
                {mainViewCase.syllabus && (
                  <div className={s.detailSection}>
                    <h3 className={s.detailSectionTitle}>Syllabus</h3>
                    <div className={s.detailText}>{mainViewCase.syllabus}</div>
                  </div>
                )}
                {mainViewCase.judges && (
                  <div className={s.detailJudges}><strong>Judges:</strong> {mainViewCase.judges}</div>
                )}
                {mainViewCase.opinion_text && (
                  <div className={s.detailSection}>
                    <h3 className={s.detailSectionTitle}>Full Opinion</h3>
                    <div className={s.detailText}>{mainViewCase.opinion_text}</div>
                  </div>
                )}
              </div>
            )}

          </>
        )}
      </div>

      {/* Floating conversation — same dock as Contracts and Matter Strategy;
          the opinion stays the page. */}
      {(caseMessages.length > 0 || caseQueryLoading) && (
        <FloatingChatDock
          open={chatOpen}
          low={composerCollapsed}
          busy={caseQueryLoading}
          count={caseMessages.length}
          onMinimize={() => setChatOpen(false)}
          onExpand={() => setChatOpen(true)}
          onClear={clearCaseConversation}
          onExport={exportCaseConversation}
          exporting={exportingCaseConversation}
          className={s.dockOffsets}
        >
          {caseMessages.map((msg: CaseMessage, msgIndex: number) => (
            <div
              key={msg.id}
              ref={msgIndex === caseMessages.length - 1 ? lastMsgRef : undefined}
              className={msg.type === 'user' ? s.messageRowUser : s.messageRow}
            >
              {msg.type === 'assistant' && (
                <div className={s.assistantAvatar}><AssistantAvatar /></div>
              )}
              <div className={msg.type === 'user' ? s.userBubble : s.assistantBubble}>
                {msg.type === 'assistant'
                  ? <><MessageMarkdown text={msg.content} /><AiNotice /></>
                  : <div className={s.messageContent}>{msg.content}</div>}
              </div>
            </div>
          ))}
          {caseQueryLoading && (
            <div className={s.messageRow}>
              <div className={s.assistantAvatar}><AssistantAvatar /></div>
              <div className={s.processingBubble}>
                <Icon name="Loader2" size={16} className={s.spinnerIcon} />
                <span>Analyzing...</span>
              </div>
            </div>
          )}
        </FloatingChatDock>
      )}

      {/* Full-page view: the whole composer collapses to a floating pill */}
      {composerCollapsed && mainViewCase && !mainViewCase.error && !caseLoading && (
        <button className={s.composerToggle} onClick={() => setComposerCollapsed(false)}>
          <Icon name="MessageSquarePlus" size={13} /> Composer
        </button>
      )}

      {/* Floating composer — identical construction to Matter Strategy and
          every tool page: chips above, pill input with circular send. */}
      {!composerCollapsed && mainViewCase && !mainViewCase.error && !caseLoading && (
        <div className={t.bottomBar}>
          <div className={t.composerToggle}>
            <button
              className={`${t.composerChip} ${!caseQueryIncludeDocs ? t.composerChipActive : ''}`}
              onClick={() => { setCaseQueryIncludeDocs(false); setCaseDocFilter(null); }}
            >
              <Icon name="Scale" size={12} /> Case Only
            </button>
            <button
              className={`${t.composerChip} ${caseQueryIncludeDocs && (!caseDocFilter || caseDocFilter.search_all) ? t.composerChipActive : ''}`}
              onClick={() => { setCaseQueryIncludeDocs(true); setCaseDocFilter({ search_all: true }); }}
            >
              <Icon name="Database" size={12} /> All My Documents
            </button>
            <button
              className={`${t.composerChip} ${caseQueryIncludeDocs && caseDocFilter && !caseDocFilter.search_all ? t.composerChipActive : ''}`}
              onClick={() => setShowCaseDocSelector(true)}
            >
              <Icon name="FileSearch" size={12} />
              {caseDocFilter && !caseDocFilter.search_all && ((caseDocFilter.document_ids?.length || 0) + (caseDocFilter.folder_paths?.length || 0)) > 0
                ? `${(caseDocFilter.document_ids?.length || 0) + (caseDocFilter.folder_paths?.length || 0)} Selected`
                : 'Select Files...'}
            </button>
          </div>
          <div className={t.searchPill}>
            <div className={s.inputTicker}>
              <input
                type="text"
                className={t.pillInput}
                aria-label={caseQueryIncludeDocs ? "Ask about this case and your documents" : "Ask about this case"}
                value={caseQueryInput}
                onChange={e => setCaseQueryInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !caseQueryLoading && caseQueryInput.trim() && queryCaseContext()}
                disabled={caseQueryLoading}
              />
              {!caseQueryInput && (
                <span key={`${caseQueryIncludeDocs}-${hintIndex}`} className={s.inputTickerHint} aria-hidden="true">
                  {composerHints[hintIndex % composerHints.length]}
                </span>
              )}
            </div>
            <button
              className={t.pillBtn}
              onClick={queryCaseContext}
              disabled={caseQueryLoading || !caseQueryInput.trim()}
            >
              {caseQueryLoading ? <Icon name="Loader2" size={16} className={t.spin} /> : <Icon name="Send" size={16} />}
            </button>
          </div>
          {/* Hints row — identical placement to Contracts and Matter Strategy */}
          <div className={s.inputHints}>
            <span>Press <kbd className={s.kbd}>Enter</kbd> to send</span>
            <button
              className={s.composerCollapseBtn}
              onClick={() => setComposerCollapsed(true)}
              title="Hide the composer for a full-page view"
            >
              <Icon name="ChevronsDown" size={12} /> Hide
            </button>
          </div>
        </div>
      )}
      </div>

      <DocumentSelector
        isOpen={showCaseDocSelector}
        onClose={() => setShowCaseDocSelector(false)}
        onSelect={(filter) => { setCaseDocFilter(filter); setCaseQueryIncludeDocs(true); }}
        currentFilter={caseDocFilter}
      />
    </div>
  );
}

export default CaseView;
