import { useEffect } from 'react';
import { useUIStore } from '../stores/uiStore';
import { useResearch } from '../contexts/ResearchContext';
import s from './RightPanel.module.css';
import { Icon, SourcesSections, SearchHistoryList, WorkspaceSessionsList } from '../components';

function RightPanel() {
  const {
    rightSidebarCollapsed, setRightSidebarCollapsed, rightPanelTab, setRightPanelTab,
    rightPanelOpen, setRightPanelOpen,
  } = useUIStore();
  const {
    allCitations, setSelectedCitation, jumpToMessage, hoveredCitationId,
    chatSessions, isLoadingSessions, currentSessionId,
    loadSession, deleteSession, handleClearSession,
  } = useResearch();

  // Slide-over drawer under the tablet breakpoint (styles/responsive.css):
  // Escape closes it; route changes close it from LeftSidebar.
  useEffect(() => {
    if (!rightPanelOpen) return;
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setRightPanelOpen(false); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [rightPanelOpen, setRightPanelOpen]);

  return (
      <>
      <div className={`sidebar-overlay ${rightPanelOpen ? 'active' : ''}`} onClick={() => setRightPanelOpen(false)} aria-hidden="true" />
      <aside id="right-panel" data-layout="right-panel" role="complementary" aria-label="Sources and history" className={`${s.rightPanel} ${rightSidebarCollapsed ? s.rightPanelCollapsed : ''} ${rightPanelOpen ? 'right-panel-open' : ''}`}>
        {/* Collapse Toggle */}
        <button
          onClick={() => setRightSidebarCollapsed(!rightSidebarCollapsed)}
          className={`${s.collapseToggle} sidebar-collapse-btn`}
          aria-label={rightSidebarCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          <Icon name={rightSidebarCollapsed ? 'ChevronLeft' : 'ChevronRight'} size={16} className={s.iconGray500} />
        </button>

        {rightSidebarCollapsed ? (
          /* Collapsed View - Icon buttons */
          <div className={s.collapsedView}>
            <button
              onClick={() => { setRightSidebarCollapsed(false); setRightPanelTab('sources'); }}
              className={`${s.collapsedBtn} ${rightPanelTab !== 'history' ? s.collapsedBtnActive : ''}`}
              title="Sources"
              aria-label="Sources"
            >
              <Icon name="FileText" size={18} className={rightPanelTab !== 'history' ? s.iconGold600 : s.iconGray500} />
            </button>
            <button
              onClick={() => { setRightSidebarCollapsed(false); setRightPanelTab('history'); }}
              className={`${s.collapsedBtn} ${rightPanelTab === 'history' ? s.collapsedBtnActive : ''}`}
              title="History"
              aria-label="History"
            >
              <Icon name="Clock" size={18} className={rightPanelTab === 'history' ? s.iconGold600 : s.iconGray500} />
            </button>
            <div className={s.collapsedDivider} />
            {allCitations.length > 0 && (
              <div className={s.collapsedCount}>{allCitations.length}</div>
            )}
          </div>
        ) : (
          <>
            <div className={s.tabBar}>
              {['sources', 'history'].map(tab => (
                <button key={tab} className={`tab-btn ${(tab === 'sources' ? rightPanelTab !== 'history' : rightPanelTab === tab) ? 'active' : ''}`} onClick={() => setRightPanelTab(tab)}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </div>

            <div className={s.rightContent}>
              {rightPanelTab === 'history' ? (
                <>
                  <SearchHistoryList
                    s={s}
                    sessions={chatSessions}
                    isLoading={isLoadingSessions}
                    currentSessionId={currentSessionId}
                    onSessionClick={loadSession}
                    onDeleteSession={deleteSession}
                    onNewChat={handleClearSession}
                  />
                  {/* Universal History: every other surface's sessions —
                      contracts, drafts, tools, judge intel, case pages. */}
                  <div className={s.rightSection}>
                    <div className={s.rightSectionTitle}>Workspace Sessions</div>
                    <WorkspaceSessionsList />
                  </div>
                </>
              ) : (
                <SourcesSections
                  panelStyles={s}
                  allCitations={allCitations}
                  setSelectedCitation={setSelectedCitation}
                  onJumpToMessage={jumpToMessage}
                  hoveredCitationId={hoveredCitationId}
                />
              )}
            </div>
          </>
        )}
      </aside>
      </>
  );
}

export { RightPanel };
export default RightPanel;
