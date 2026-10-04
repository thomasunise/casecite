import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToolsStore } from '../stores/toolsStore';
import type { ToolChatMessage } from '../stores/toolsStore';
import { useCaseViewStore } from '../stores/caseViewStore';
import { useJudgeIntelStore } from '../stores/judgeIntelStore';
import { TOOLS_WITH_RESULT_CHAT } from '../constants/tools';
import { MODE_TO_ROUTE } from '../routeConfig';
import { Icon, ToolResultsArea, FloatingChatDock, AssistantAvatar, MessageMarkdown, AiNotice } from '../components';
import type { CaseInfo } from '../types';
import type { ToolResultData } from '../components/shared/ToolResultsArea';
import type { DocketDetail } from '../components/shared/DocketDetailView';
import rp from '../layout/RightPanel.module.css';
import s from './ToolsView.module.css';

function ToolsView() {
  const {
    activeTool, setActiveTool,
    toolLoading, toolApiSlow, toolResult, setToolResult, toolInput, setToolInput,
    handleToolSearch, loadMoreResults,
    selectedCase: rawSelectedCase, setSelectedCase, caseLoading,
    selectedJudge, setSelectedJudge,
    selectedDocket, setSelectedDocket, docketLoading, loadDocketDetail,
    loadPrecedentCase,
    toolChatMessages, toolChatInput, setToolChatInput, toolChatLoading, sendToolChat, clearToolChat, exportToolChat, exportingToolChat,
  } = useToolsStore();
  const { loadCaseDetail } = useCaseViewStore();
  const { buildJudgeIntel } = useJudgeIntelStore();

  const navigate = useNavigate();
  const setActiveMode = (mode: string) => navigate(MODE_TO_ROUTE[mode] || '/research');

  // Bottom composer mode: defaults to a new search; the user opts in to chat.
  const [composerMode, setComposerMode] = useState<'chat' | 'search'>('search');
  // Result-chat lives in the same floating dock as every other chat page.
  const [chatOpen, setChatOpen] = useState(true);
  useEffect(() => {
    if (toolChatMessages.length > 0) setChatOpen(true);
  }, [toolChatMessages.length]);

  const tr = toolResult as ToolResultData | null;
  const selectedCase = rawSelectedCase as CaseInfo | null;

  if (!activeTool) {
    return (
      <div className={s.toolsView}>
        <div className={s.emptyState}>
          <Icon name="Wrench" size={36} className={s.emptyIcon} />
          <h2 className={s.emptyTitle}>Legal Tools</h2>
          <p className={s.emptyText}>
            Pick a tool from the sidebar to search case law, check a citation for
            negative treatment, analyze a judge, and more — right here in the main area.
          </p>
        </div>
      </div>
    );
  }

  const showChat =
    TOOLS_WITH_RESULT_CHAT.includes(activeTool.id) && !!tr && !tr.error && !selectedCase && !selectedDocket;
  // Centered "floating search" until a query is run, then it fades to results.
  const showHero = !tr && !toolLoading && !selectedCase;

  return (
    <div className={s.toolsView}>
      {showHero ? (
        <div className={s.hero}>
          <h1 className={s.heroTitle}>{activeTool.name}</h1>
          {activeTool.desc ? <p className={s.heroSubtitle}>{activeTool.desc as string}</p> : null}
          <div className={s.searchPill}>
            <input
              aria-label={`${activeTool.name} search`}
              type="text"
              className={s.pillInput}
              placeholder={activeTool.placeholder}
              value={toolInput}
              onChange={(e) => setToolInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && toolInput.trim() && handleToolSearch()}
              autoFocus
            />
            <button className={s.pillBtn} onClick={() => handleToolSearch()} disabled={!toolInput.trim() || toolLoading}>
              <Icon name="Search" size={16} />
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className={s.resultsScroll}>
            <ToolResultsArea
              s={rp}
              tr={tr}
              activeTool={activeTool}
              toolInput={toolInput}
              toolLoading={toolLoading}
              toolApiSlow={toolApiSlow}
              selectedCase={selectedCase}
              selectedJudge={selectedJudge}
              caseLoading={caseLoading}
              selectedDocket={selectedDocket as DocketDetail | null}
              docketLoading={docketLoading}
              loadDocketDetail={loadDocketDetail}
              setSelectedDocket={setSelectedDocket}
              loadPrecedentCase={loadPrecedentCase}
              loadCaseDetail={loadCaseDetail}
              setSelectedCase={setSelectedCase}
              setSelectedJudge={setSelectedJudge}
              loadMoreResults={loadMoreResults}
              setActiveMode={setActiveMode}
              setActiveTool={setActiveTool}
              setToolResult={setToolResult}
              buildJudgeIntel={buildJudgeIntel}
            />

          </div>

          {/* Result-chat floats in the same dock as every other chat page —
              the results stay the page underneath. */}
          {showChat && (toolChatMessages.length > 0 || toolChatLoading) && (
            <FloatingChatDock
              open={chatOpen}
              busy={toolChatLoading}
              count={toolChatMessages.length}
              onMinimize={() => setChatOpen(false)}
              onExpand={() => setChatOpen(true)}
              onClear={clearToolChat}
              onExport={exportToolChat}
              exporting={exportingToolChat}
              className={s.dockOffsets}
            >
              {toolChatMessages.map((m: ToolChatMessage) => (
                <div key={m.id} className={m.type === 'user' ? s.msgRowUser : s.msgRow}>
                  {m.type === 'assistant' && <div className={s.avatar}><AssistantAvatar /></div>}
                  <div className={m.type === 'user' ? s.userBubble : s.assistantBubble}>
                    {m.type === 'assistant' ? <><MessageMarkdown text={m.content} /><AiNotice /></> : m.content}
                  </div>
                </div>
              ))}
              {toolChatLoading && (
                <div className={s.msgRow}>
                  <div className={s.avatar}><AssistantAvatar /></div>
                  <div className={s.processingBubble}>
                    <Icon name="Loader2" size={14} className={s.spin} /> Analyzing...
                  </div>
                </div>
              )}
            </FloatingChatDock>
          )}

          {/* Floating composer at the bottom once results are showing.
              When the tool supports result-chat, offer a toggle so the user can
              either chat about the results or kick off a brand-new search. */}
          <div className={s.bottomBar}>
            {showChat && (
              <div className={s.composerToggle}>
                <button
                  className={`${s.composerChip} ${composerMode === 'chat' ? s.composerChipActive : ''}`}
                  onClick={() => setComposerMode('chat')}
                >
                  <Icon name="MessagesSquare" size={13} /> Chat with this
                </button>
                <button
                  className={`${s.composerChip} ${composerMode === 'search' ? s.composerChipActive : ''}`}
                  onClick={() => setComposerMode('search')}
                >
                  <Icon name="Search" size={13} /> New search
                </button>
              </div>
            )}
            <div className={s.searchPill}>
              {showChat && composerMode === 'chat' ? (
                <>
                  <input
                    aria-label="Ask about these results"
                    type="text"
                    className={s.pillInput}
                    placeholder="Ask about these results..."
                    value={toolChatInput}
                    onChange={(e) => setToolChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !toolChatLoading && toolChatInput.trim() && sendToolChat()}
                    disabled={toolChatLoading}
                  />
                  <button className={s.pillBtn} onClick={sendToolChat} disabled={toolChatLoading || !toolChatInput.trim()}>
                    {toolChatLoading ? <Icon name="Loader2" size={16} className={s.spin} /> : <Icon name="Send" size={16} />}
                  </button>
                </>
              ) : (
                <>
                  <input
                    aria-label={`New ${activeTool.name} search`}
                    type="text"
                    className={s.pillInput}
                    placeholder={`New search — ${activeTool.placeholder}`}
                    value={toolInput}
                    onChange={(e) => setToolInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && toolInput.trim() && handleToolSearch()}
                  />
                  <button className={s.pillBtn} onClick={() => handleToolSearch()} disabled={!toolInput.trim() || toolLoading}>
                    {toolLoading ? <Icon name="Loader2" size={16} className={s.spin} /> : <Icon name="Search" size={16} />}
                  </button>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default ToolsView;
