import { useJudgeIntelStore } from '../stores/judgeIntelStore';
import type { DocumentFilter } from '../types';
import s from './JudgeIntelView.module.css';
// Shared tool-page shell: scrolling results + the app-wide floating composer.
import t from './ToolsView.module.css';
import { Icon, JudgeSearchPanel, JudgeBriefTab, JudgeProfileTab, JudgeOpinionsTab, JudgeStatsSection, JudgeMetricsSection, DocumentSelector } from '../components';
import { safeHttpUrl } from '../components/shared/safeUrl';

function JudgeIntelView() {
  const {
    judgeIntelBuilding,
    judgeIntelBuildProgress,
    judgeIntelProfile,
    judgeIntelResults,
    judgeIntelSearch,
    setJudgeIntelSearch,
    searchJudgesIntel,
    judgeIntelLoading,
    judgeIntelStats,
    judgeIntelMetrics,
    judgeIntelMetricsLoading,
    judgeIntelOpinionsLoading,
    rebuildJudgeIntel,
    judgeIntelOpinions,
    judgeIntelOpinionQuery,
    setJudgeIntelOpinionQuery,
    judgeIntelOpinionSort,
    queryJudgeOpinions,
    selectedOpinion,
    setSelectedOpinion,
    loadOpinionFullText,
    judgeBrief,
    judgeBriefLoading,
    generateJudgeBrief,
    judgeMessages,
    judgeQueryInput,
    setJudgeQueryInput,
    judgeQueryLoading,
    queryJudgeContext,
    judgeQueryIncludeDocs,
    clearJudgeConversation,
    setJudgeQueryIncludeDocs,
    showJudgeDocSelector,
    setShowJudgeDocSelector,
    judgeDocFilter,
    setJudgeDocFilter,
    backToJudgeSearch,
    buildJudgeIntel,
  } = useJudgeIntelStore();

  const totalOpinions = judgeIntelProfile?.opinion_stats?.total_opinions ?? 0;
  const totalCitations = judgeIntelProfile?.opinion_stats?.total_citations ?? 0;
  const avgCitations = totalOpinions > 0 ? (totalCitations / totalOpinions).toFixed(1) : '—';
  const selectedDocCount = judgeDocFilter && !judgeDocFilter.search_all
    ? (judgeDocFilter.document_ids?.length || 0) + (judgeDocFilter.folder_paths?.length || 0)
    : 0;

  return (
    <div className={s.judgeIntelArea}>
      {judgeIntelBuilding ? (
        /* Loading State - Building Profile */
        <div className={s.judgeIntelBuilding}>
          <Icon name="Loader2" size={32} className={s.buildingSpinner} />
          <h3 className={s.buildingTitle}>Building Judge Intelligence Profile</h3>
          <span className={s.buildingProgress}>{judgeIntelBuildProgress || 'Pulling all available data...'}</span>
          <p className={s.buildingNote}>This may take a moment for judges with many opinions.</p>
        </div>
      ) : !judgeIntelProfile ? (
        /* Judge Search View */
        <JudgeSearchPanel
          s={s}
          judgeIntelSearch={judgeIntelSearch}
          setJudgeIntelSearch={setJudgeIntelSearch}
          searchJudgesIntel={searchJudgesIntel}
          judgeIntelLoading={judgeIntelLoading}
          judgeIntelResults={judgeIntelResults}
          buildJudgeIntel={buildJudgeIntel}
        />
      ) : (
        /* Judge Profile — one page: profile, record, opinions, then AI.
           Same shell as every tool page: scrolling results + the app-wide
           floating composer for "Ask About This Judge". */
        <div className={t.toolsView}>
          <div className={`${t.resultsScroll} ${s.profilePage}`}>
            <div className={s.profileToolbar}>
              <button className={s.judgeIntelBackBtn} onClick={backToJudgeSearch}>
                <Icon name="ChevronLeft" size={14} /> Back to Search
              </button>
              {!judgeIntelProfile.error && (
                <button
                  className={s.judgeIntelBackBtn}
                  onClick={rebuildJudgeIntel}
                  title="Re-pull opinions, dockets and biography from CourtListener"
                >
                  <Icon name="RefreshCw" size={13} /> Rebuild profile
                </button>
              )}
            </div>

            {judgeIntelProfile.error ? (
              <div className={s.toolErrorBox}><Icon name="AlertCircle" size={14} /> {judgeIntelProfile.error}</div>
            ) : (
              <div className={s.profileCard}>
                <div className={s.profileHeader}>
                  <p className={s.profileOverline}>Judge Intelligence · CourtListener</p>
                  <h2 className={s.judgeProfileName}>
                    {judgeIntelProfile.name}
                    {judgeIntelProfile.wikipedia_url && (
                      <a href={safeHttpUrl(judgeIntelProfile.wikipedia_url) ?? undefined} target="_blank" rel="noopener noreferrer"
                         className={s.wikiLink}>
                        <Icon name="ExternalLink" size={11} className={s.wikiLinkIcon} />Wikipedia
                      </a>
                    )}
                  </h2>
                  <div className={s.judgeProfileMeta}>
                    {judgeIntelProfile.gender && <span>{judgeIntelProfile.gender}</span>}
                    {judgeIntelProfile.date_of_birth && <span>Born {judgeIntelProfile.date_of_birth}</span>}
                    {judgeIntelProfile.place_of_birth_city && <span>{judgeIntelProfile.place_of_birth_city}, {judgeIntelProfile.place_of_birth_state}</span>}
                    {judgeIntelProfile.political_affiliation && <span>{judgeIntelProfile.political_affiliation}</span>}
                    {judgeIntelProfile.courtlistener_url ? (
                      <a href={safeHttpUrl(judgeIntelProfile.courtlistener_url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.wikiLink}>
                        <Icon name="ExternalLink" size={11} className={s.wikiLinkIcon} />CourtListener
                      </a>
                    ) : null}
                    {judgeIntelProfile.data_pulled_at ? (
                      <span className={s.dataQuality}>Data pulled {String(judgeIntelProfile.data_pulled_at).slice(0, 10)}</span>
                    ) : null}
                  </div>
                </div>

                <div className={s.metricsRow}>
                  {[
                    { label: 'Opinions', value: totalOpinions.toLocaleString() },
                    { label: 'Citations', value: totalCitations.toLocaleString() },
                    { label: 'Cases', value: (judgeIntelProfile.docket_stats?.total_dockets ?? 0).toLocaleString() },
                    { label: 'Avg Cites/Op', value: avgCitations },
                  ].map((m, i) => (
                    <div key={i} className={s.metricBox}>
                      <span className={`${s.metricValue} mono`}>{m.value}</span>
                      <span className={s.metricLabel}>{m.label}</span>
                    </div>
                  ))}
                </div>

                <div className={s.profileBody}>
                  <JudgeProfileTab
                    s={s}
                    judgeIntelProfile={judgeIntelProfile}
                  />

                  <JudgeStatsSection
                    s={s}
                    judgeIntelStats={judgeIntelStats}
                  />

                  <JudgeMetricsSection
                    s={s}
                    metrics={judgeIntelMetrics}
                    loading={judgeIntelMetricsLoading}
                  />

                  <JudgeOpinionsTab
                    s={s}
                    judgeId={judgeIntelProfile.id}
                    selectedOpinion={selectedOpinion}
                    setSelectedOpinion={setSelectedOpinion}
                    loadOpinionFullText={loadOpinionFullText}
                    judgeIntelOpinionQuery={judgeIntelOpinionQuery}
                    setJudgeIntelOpinionQuery={setJudgeIntelOpinionQuery}
                    judgeIntelOpinionSort={judgeIntelOpinionSort}
                    queryJudgeOpinions={queryJudgeOpinions}
                    judgeIntelLoading={judgeIntelOpinionsLoading}
                    judgeIntelOpinions={judgeIntelOpinions}
                  />

                  <JudgeBriefTab
                    s={s}
                    judgeIntelProfile={judgeIntelProfile}
                    judgeBrief={judgeBrief}
                    judgeBriefLoading={judgeBriefLoading}
                    generateJudgeBrief={generateJudgeBrief}
                    judgeMessages={judgeMessages}
                    setJudgeQueryInput={setJudgeQueryInput}
                    judgeQueryLoading={judgeQueryLoading}
                    judgeQueryIncludeDocs={judgeQueryIncludeDocs}
                    clearJudgeConversation={clearJudgeConversation}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Floating composer — identical construction to Matter Strategy
              and the tool pages: chips above, pill input with circular send. */}
          {!judgeIntelProfile.error && (
            <div className={t.bottomBar}>
              <div className={t.composerToggle}>
                <button
                  className={`${t.composerChip} ${!judgeQueryIncludeDocs ? t.composerChipActive : ''}`}
                  onClick={() => { setJudgeQueryIncludeDocs(false); setJudgeDocFilter(null); }}
                >
                  <Icon name="Gavel" size={12} /> Judge Data Only
                </button>
                <button
                  className={`${t.composerChip} ${judgeQueryIncludeDocs && (!judgeDocFilter || judgeDocFilter.search_all) ? t.composerChipActive : ''}`}
                  onClick={() => { setJudgeQueryIncludeDocs(true); setJudgeDocFilter({ search_all: true }); }}
                >
                  <Icon name="Database" size={12} /> All My Documents
                </button>
                <button
                  className={`${t.composerChip} ${judgeQueryIncludeDocs && selectedDocCount > 0 ? t.composerChipActive : ''}`}
                  onClick={() => setShowJudgeDocSelector(true)}
                >
                  <Icon name="FileSearch" size={12} />
                  {selectedDocCount > 0 ? `${selectedDocCount} Selected` : 'Select Files...'}
                </button>
              </div>
              <div className={t.searchPill}>
                <input
                  aria-label="Ask about this judge"
                  type="text"
                  className={t.pillInput}
                  placeholder={judgeQueryIncludeDocs ? 'Ask about this judge in relation to your documents...' : "Ask about this judge's rulings, patterns, or philosophy..."}
                  value={judgeQueryInput}
                  onChange={(e) => setJudgeQueryInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !judgeQueryLoading && queryJudgeContext()}
                  disabled={judgeQueryLoading}
                />
                <button
                  className={t.pillBtn}
                  onClick={queryJudgeContext}
                  disabled={judgeQueryLoading || !judgeQueryInput.trim()}
                >
                  {judgeQueryLoading ? <Icon name="Loader2" size={16} className={t.spin} /> : <Icon name="Send" size={16} />}
                </button>
              </div>
            </div>
          )}

          <DocumentSelector
            isOpen={showJudgeDocSelector}
            onClose={() => setShowJudgeDocSelector(false)}
            onSelect={(filter: DocumentFilter) => { setJudgeDocFilter(filter); setJudgeQueryIncludeDocs(true); }}
            currentFilter={judgeDocFilter}
          />
        </div>
      )}
    </div>
  );
}

export default JudgeIntelView;
