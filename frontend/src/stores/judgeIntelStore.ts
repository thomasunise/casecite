import { create } from 'zustand';
import { registerReset } from './resetRegistry';
import { api, API_BASE_URL } from '../api';
import { formatErrorDetail } from '../api/client';
import { persistWorkspaceSession, resetWorkspaceSessionKey } from './workspaceSessionsStore';
import logger from '../utils/logger';
import { useUIStore } from './uiStore';
import type {
  JudgeSearchResponse, JudgeIntelProfile, JudgeStats, JudgeMetrics,
  JudgeMessage, DocumentFilter, JudgeEducation, JudgePosition,
  OpinionEntry, DocketEntry, OpinionListResponse, OpinionSummary,
} from '../types';

export type JudgeOpinionSort = 'citations' | 'date';

export interface JudgeIntelState {
  // Search & profile
  judgeIntelSearch: string;
  setJudgeIntelSearch: (val: string) => void;
  judgeIntelResults: JudgeSearchResponse | null;
  judgeIntelProfile: JudgeIntelProfile | null;
  judgeIntelStats: JudgeStats | null;
  judgeIntelMetrics: JudgeMetrics | null;
  judgeIntelMetricsLoading: boolean;
  judgeIntelOpinionsLoading: boolean;
  judgeIntelLoading: boolean;
  judgeIntelBuilding: boolean;
  judgeIntelBuildProgress: string;
  // Brief sub-state
  judgeBrief: string | null;
  judgeBriefLoading: boolean;
  judgeMessages: JudgeMessage[];
  judgeQueryInput: string;
  setJudgeQueryInput: (val: string) => void;
  judgeQueryLoading: boolean;
  judgeQueryIncludeDocs: boolean;
  clearJudgeConversation: () => void;
  setJudgeQueryIncludeDocs: (val: boolean) => void;
  judgeDocFilter: DocumentFilter | null;
  setJudgeDocFilter: (val: DocumentFilter | null) => void;
  showJudgeDocSelector: boolean;
  setShowJudgeDocSelector: (val: boolean) => void;
  // Opinion sub-state
  judgeIntelOpinions: OpinionListResponse | null;
  judgeIntelOpinionQuery: string;
  setJudgeIntelOpinionQuery: (val: string) => void;
  judgeIntelOpinionSort: JudgeOpinionSort;
  selectedOpinion: OpinionSummary | null;
  setSelectedOpinion: (val: OpinionSummary | null) => void;
  // Actions
  searchJudgesIntel: () => Promise<void>;
  buildJudgeIntel: (judgeId: string | number, judgeName: string, forceRefresh?: boolean) => Promise<void>;
  /** Re-pull everything from CourtListener for the judge on screen. */
  rebuildJudgeIntel: () => Promise<void>;
  loadJudgeIntelStats: (judgeId: string | number) => Promise<void>;
  loadJudgeIntelMetrics: (judgeId: string | number) => Promise<void>;
  backToJudgeSearch: () => void;
  generateJudgeBrief: (profile: JudgeIntelProfile) => Promise<void>;
  queryJudgeContext: () => Promise<void>;
  queryJudgeOpinions: (
    judgeId: string | number, query?: string, offset?: number, sort?: JudgeOpinionSort
  ) => Promise<void>;
  loadOpinionFullText: (judgeId: string | number, opinionId: string | number) => Promise<void>;
  /** Rebuild a judge session (profile + Q&A + brief) from History. */
  restoreWorkspaceSession: (payload: Record<string, unknown>) => Promise<void>;
}

export const useJudgeIntelStore = create<JudgeIntelState>((set, get) => {
  // Universal History: the judge Q&A + brief snapshot; the profile itself is
  // rebuilt from the local judge cache on restore.
  const persistJudgeSession = () => {
    const { judgeIntelProfile, judgeMessages, judgeBrief } = get();
    if (!judgeIntelProfile?.id) return;
    persistWorkspaceSession('judge', 'judge', `Judge: ${judgeIntelProfile.name || judgeIntelProfile.id}`, {
      judgeId: judgeIntelProfile.id,
      judgeName: judgeIntelProfile.name || '',
      judgeMessages,
      judgeBrief,
    });
  };

  return ({
  // Search & profile
  judgeIntelSearch: '',
  setJudgeIntelSearch: (val) => set({ judgeIntelSearch: val }),
  judgeIntelResults: null,
  judgeIntelProfile: null,
  judgeIntelStats: null,
  judgeIntelMetrics: null,
  judgeIntelMetricsLoading: false,
  judgeIntelOpinionsLoading: false,
  judgeIntelLoading: false,
  judgeIntelBuilding: false,
  judgeIntelBuildProgress: '',

  // Brief sub-state
  judgeBrief: null,
  judgeBriefLoading: false,
  judgeMessages: [],
  judgeQueryInput: '',
  setJudgeQueryInput: (val) => set({ judgeQueryInput: val }),
  judgeQueryLoading: false,
  judgeQueryIncludeDocs: false,
  setJudgeQueryIncludeDocs: (val) => set({ judgeQueryIncludeDocs: val }),
  clearJudgeConversation: () =>
    set({ judgeMessages: [], judgeQueryInput: '', judgeQueryLoading: false }),
  judgeDocFilter: null,
  setJudgeDocFilter: (val) => set({ judgeDocFilter: val }),
  showJudgeDocSelector: false,
  setShowJudgeDocSelector: (val) => set({ showJudgeDocSelector: val }),

  // Opinion sub-state
  judgeIntelOpinions: null,
  judgeIntelOpinionQuery: '',
  setJudgeIntelOpinionQuery: (val) => set({ judgeIntelOpinionQuery: val }),
  judgeIntelOpinionSort: 'citations',
  selectedOpinion: null,
  setSelectedOpinion: (val) => set({ selectedOpinion: val }),

  // Actions
  loadJudgeIntelStats: async (judgeId) => {
    try {
      const response = await api.authFetch(`${API_BASE_URL}/judge-intel/profile/${judgeId}/stats`);
      if (response.ok) {
        const data = await response.json();
        set({ judgeIntelStats: data });
      } else {
        useUIStore.getState().addToast('Could not load judge statistics.', 'error');
      }
    } catch (error: unknown) {
      logger.error('Stats error:', error);
      useUIStore.getState().addToast('Could not load judge statistics.', 'error');
    }
  },

  loadJudgeIntelMetrics: async (judgeId) => {
    set({ judgeIntelMetricsLoading: true });
    try {
      const response = await api.authFetch(`${API_BASE_URL}/judge-intel/profile/${judgeId}/metrics`);
      if (response.ok) {
        set({ judgeIntelMetrics: await response.json() });
      } else {
        const errorData = await response.json().catch(() => ({}));
        set({ judgeIntelMetrics: { metrics: {}, error: formatErrorDetail(errorData.detail, 'Analytics unavailable') } });
      }
    } catch (error: unknown) {
      logger.error('Metrics error:', error);
      set({ judgeIntelMetrics: { metrics: {}, error: 'Analytics unavailable' } });
    }
    set({ judgeIntelMetricsLoading: false });
  },

  rebuildJudgeIntel: async () => {
    const { judgeIntelProfile } = get();
    if (!judgeIntelProfile?.id) return;
    await get().buildJudgeIntel(judgeIntelProfile.id, judgeIntelProfile.name || '', true);
  },

  searchJudgesIntel: async () => {
    const { judgeIntelSearch } = get();
    if (!judgeIntelSearch.trim()) return;
    set({ judgeIntelLoading: true, judgeIntelResults: null, judgeIntelProfile: null });
    try {
      const response = await api.authFetch(`${API_BASE_URL}/judge-intel/search?q=${encodeURIComponent(judgeIntelSearch)}&limit=500`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(formatErrorDetail(errorData.detail, 'Search failed'));
      }
      const data = await response.json();
      set({ judgeIntelResults: data });
    } catch (error: unknown) {
      logger.error('Judge Intel search error:', error);
      set({ judgeIntelResults: { error: error instanceof Error ? error.message : String(error) } });
    }
    set({ judgeIntelLoading: false });
  },

  buildJudgeIntel: async (judgeId, judgeName, forceRefresh = false) => {
    // A new judge is a new History session.
    resetWorkspaceSessionKey('judge');
    set({
      judgeIntelBuilding: true,
      judgeIntelBuildProgress: forceRefresh
        ? `Re-pulling everything CourtListener has on ${judgeName}...`
        : `Starting analysis of ${judgeName}...`,
      judgeIntelProfile: null,
      judgeIntelStats: null,
      judgeIntelMetrics: null,
      judgeIntelOpinions: null,
      judgeIntelOpinionQuery: '',
      judgeIntelOpinionSort: 'citations',
      selectedOpinion: null,
      judgeBrief: null,
      judgeMessages: [],
      judgeQueryInput: '',
    });

    try {
      const response = await api.authFetch(
        `${API_BASE_URL}/judge-intel/build/${judgeId}${forceRefresh ? '?force_refresh=true' : ''}`,
        // A full build makes 100+ paced CourtListener calls; give it real time.
        { method: 'POST', timeout: 600000 },
      );
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(formatErrorDetail(errorData.detail, 'Build failed'));
      }
      const data = await response.json();
      set({ judgeIntelProfile: data.profile, judgeIntelBuildProgress: '', judgeBrief: null });
      // The page shows opinions and statistics inline (no tabs) — load both
      // right away. Opinions default to most-cited order.
      get().queryJudgeOpinions(judgeId);
      get().loadJudgeIntelStats(judgeId);
      get().loadJudgeIntelMetrics(judgeId);
    } catch (error: unknown) {
      logger.error('Build intel error:', error);
      set({ judgeIntelProfile: { error: error instanceof Error ? error.message : String(error) } as JudgeIntelProfile });
    }
    set({ judgeIntelBuilding: false });
  },

  backToJudgeSearch: () => {
    set({
      judgeIntelProfile: null,
      judgeIntelStats: null,
      judgeIntelOpinions: null,
      judgeIntelOpinionQuery: '',
      judgeIntelOpinionSort: 'citations',
      selectedOpinion: null,
      judgeBrief: null,
      judgeMessages: [],
      judgeQueryInput: '',
    });
  },

  generateJudgeBrief: async (profile) => {
    if (!profile || profile.error) return;
    set({ judgeBriefLoading: true });
    try {
      const educationDetails = profile.education?.map((e: JudgeEducation) =>
        `- ${e.school_name}: ${e.degree || 'Degree'} (${e.degree_year || 'Year unknown'})${e.school_type ? ` [${e.school_type}]` : ''}`
      ).join('\n') || 'No education data available';

      const positionsDetails = profile.positions?.map((p: JudgePosition) =>
        `- ${p.position_type || 'Position'} at ${p.court_name}\n  Appointed by: ${p.appointer || 'Unknown'}\n  Period: ${p.date_start || '?'} to ${p.date_termination || 'present'}${p.termination_reason ? ` (${p.termination_reason})` : ''}`
      ).join('\n') || 'No position data available';

      const topCasesDetails = profile.most_cited_opinions?.slice(0, 15).map((c: OpinionEntry, i: number) =>
        `${i+1}. ${c.case_name}\n   Citation: ${c.citation || 'N/A'} | Court: ${c.court || 'N/A'} | Date: ${c.date_filed || 'N/A'}\n   Citations received: ${c.citation_count || 0}`
      ).join('\n') || 'No opinion data available';

      const courtBreakdown = profile.opinions_by_court?.map((c: { court: string; count: number }) =>
        `- ${c.court}: ${c.count} opinions`
      ).join('\n') || 'No court data';

      const careerYears = profile.opinion_stats?.first_opinion && profile.opinion_stats?.last_opinion
        ? `${profile.opinion_stats.first_opinion.substring(0,4)} - ${profile.opinion_stats.last_opinion.substring(0,4)}`
        : 'Unknown span';

      const avgCitations = (profile.opinion_stats?.total_opinions ?? 0) > 0
        ? ((profile.opinion_stats?.total_citations ?? 0) / (profile.opinion_stats?.total_opinions ?? 1)).toFixed(1)
        : 'N/A';

      const hasWikipedia = profile.wikipedia_url || profile.wikipedia_summary;
      const wikipediaSection = hasWikipedia ? `
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
WIKIPEDIA BIOGRAPHICAL DATA:
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
${profile.wikipedia_url ? `Source: ${profile.wikipedia_url}` : ''}

${profile.wikipedia_summary ? `SUMMARY:\n${profile.wikipedia_summary}\n` : ''}
${profile.wikipedia_early_life ? `EARLY LIFE:\n${profile.wikipedia_early_life}\n` : ''}
${profile.wikipedia_education ? `EDUCATION (Wikipedia):\n${profile.wikipedia_education}\n` : ''}
${profile.wikipedia_career ? `CAREER:\n${profile.wikipedia_career}\n` : ''}
${profile.wikipedia_judicial_service ? `JUDICIAL SERVICE:\n${profile.wikipedia_judicial_service}\n` : ''}
${profile.wikipedia_notable_cases ? `NOTABLE CASES (Wikipedia):\n${profile.wikipedia_notable_cases}\n` : ''}
${profile.wikipedia_personal_life ? `PERSONAL LIFE:\n${profile.wikipedia_personal_life}\n` : ''}
` : '';

      const hasDockets = (profile.docket_stats?.total_dockets ?? 0) > 0;
      const response = await api.authFetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        // Case-law answers read full opinions — same budget as api.query.
        timeout: 180000,
        body: JSON.stringify({
          query: `CRITICAL INSTRUCTIONS - READ CAREFULLY:
You are writing a COMPLETED judicial intelligence brief. You must write ACTUAL ANALYSIS based ONLY on the data provided below.

DO NOT:
- Write templates or frameworks
- Say "research this" or "compile information" or "investigate"
- Give instructions to the reader
- Include placeholder text
- Suggest the reader do research

DO:
- Write finished, substantive paragraphs
- Make specific observations from the actual data provided
- If a section has no data, write ONE sentence noting it's unavailable and move on
- Be direct and analytical, not instructional

Write in past/present tense as a completed analysis, not as instructions.

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
JUDGE: ${profile.name}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

## QUICK FACTS
Write 3-4 bullet points summarizing the key facts about this judge that an attorney needs to know immediately.

## BACKGROUND
${profile.date_of_birth ? `Born ${profile.date_of_birth}` : ''}${profile.place_of_birth_city ? ` in ${profile.place_of_birth_city}${profile.place_of_birth_state ? ', ' + profile.place_of_birth_state : ''}` : ''}.
${profile.political_affiliation ? `Political affiliation: ${profile.political_affiliation}.` : ''}
${profile.gender ? `Gender: ${profile.gender}.` : ''}
Write 2-3 sentences summarizing their background based on available data.

## EDUCATION
${educationDetails}
Write 2-3 sentences about their educational background and what it might indicate about their legal training.

## CAREER & APPOINTMENTS
${positionsDetails}
Write a paragraph summarizing their career path based on the positions listed above.

## JUDICIAL RECORD ANALYSIS
- Total Opinions: ${profile.opinion_stats?.total_opinions || 0}
- Total Citations: ${profile.opinion_stats?.total_citations || 0}
- Avg Citations/Opinion: ${avgCitations}
- Active Period: ${careerYears}

Based on these numbers, write 2-3 sentences analyzing their judicial output and influence.

## NOTABLE CASES
${topCasesDetails}

Write a paragraph analyzing their most-cited opinions. What areas of law do they appear in? What does their citation count suggest about their influence?

## COURTROOM STRATEGY
Based on all the data above, write 4-5 specific, actionable bullet points for attorneys appearing before this judge. What approaches might work? What should they avoid? Be specific based on the actual case types and rulings shown.

Courts where they've ruled: ${courtBreakdown}
${wikipediaSection}
${hasDockets ? `\nASSIGNED CASES: ${profile.docket_stats?.total_dockets || 0} total cases assigned. Types: ${profile.dockets_by_type?.slice(0,5).map((d: { nature_of_suit: string; count: number }) => d.nature_of_suit).join(', ') || 'Various'}` : ''}`,
          mode: 'research',
          include_documents: false,
          include_case_law: false,
        }),
      });
      if (!response.ok) throw new Error('Failed to generate brief');
      const data = await response.json();
      set({ judgeBrief: data.content });
      persistJudgeSession();
    } catch (error: unknown) {
      logger.error('Judge brief error:', error);
      set({ judgeBrief: 'Unable to generate brief. You can still view the profile data and query about this judge below.' });
    }
    set({ judgeBriefLoading: false });
  },

  queryJudgeContext: async () => {
    const { judgeQueryInput, judgeIntelProfile, judgeQueryIncludeDocs, judgeDocFilter } = get();
    if (!judgeQueryInput.trim() || !judgeIntelProfile) return;
    const userQuery = judgeQueryInput.trim();
    set({ judgeQueryInput: '', judgeQueryLoading: true });

    const userMsg: JudgeMessage = { id: Date.now(), type: 'user', content: userQuery };
    set((state) => ({ judgeMessages: [...state.judgeMessages, userMsg] }));

    try {
      const topCases = judgeIntelProfile.most_cited_opinions?.slice(0, 20).map((c: OpinionEntry, i: number) =>
        `${i+1}. ${c.case_name} (${c.citation || 'N/A'}) - ${c.citation_count} citations - ${c.date_filed || 'N/A'} - ${c.court || ''}`
      ).join('\n') || 'None';

      const positions = judgeIntelProfile.positions?.map((p: JudgePosition) =>
        `- ${p.position_type} at ${p.court_name} (${p.date_start || '?'} - ${p.date_termination || 'present'}) appointed by ${p.appointer || 'unknown'}`
      ).join('\n') || 'None';

      const education = judgeIntelProfile.education?.map((e: JudgeEducation) =>
        `- ${e.school_name}: ${e.degree || 'Degree'} (${e.degree_year || '?'})`
      ).join('\n') || 'None';

      const courtBreakdown = judgeIntelProfile.opinions_by_court?.map((c: { court: string; count: number }) => `${c.court}: ${c.count}`).join(', ') || 'None';
      const yearlyTrend = judgeIntelProfile.opinions_by_year?.map((y: { year: number; count: number }) => `${y.year}:${y.count}`).join(', ') || 'None';

      const hasWiki = judgeIntelProfile.wikipedia_url || judgeIntelProfile.wikipedia_summary;
      const wikiContext = hasWiki ? `
WIKIPEDIA BIOGRAPHICAL DATA:
${judgeIntelProfile.wikipedia_summary ? `Summary: ${judgeIntelProfile.wikipedia_summary}` : ''}
${judgeIntelProfile.wikipedia_early_life ? `Early Life: ${judgeIntelProfile.wikipedia_early_life}` : ''}
${judgeIntelProfile.wikipedia_education ? `Education: ${judgeIntelProfile.wikipedia_education}` : ''}
${judgeIntelProfile.wikipedia_career ? `Career: ${judgeIntelProfile.wikipedia_career}` : ''}
${judgeIntelProfile.wikipedia_judicial_service ? `Judicial Service: ${judgeIntelProfile.wikipedia_judicial_service}` : ''}
${judgeIntelProfile.wikipedia_notable_cases ? `Notable Cases: ${judgeIntelProfile.wikipedia_notable_cases}` : ''}
${judgeIntelProfile.wikipedia_personal_life ? `Personal Life: ${judgeIntelProfile.wikipedia_personal_life}` : ''}
` : '';

      const hasDocketData = (judgeIntelProfile.docket_stats?.total_dockets ?? 0) > 0;
      const docketContext = hasDocketData ? `
ASSIGNED CASES/DOCKETS:
- Total Assigned: ${judgeIntelProfile.docket_stats?.total_dockets}
- Case Types: ${judgeIntelProfile.dockets_by_type?.map((d: { nature_of_suit: string; count: number }) => `${d.nature_of_suit}: ${d.count}`).join(', ') || 'N/A'}
- Recent Cases: ${judgeIntelProfile.recent_dockets?.slice(0,5).map((d: DocketEntry) => d.case_name).join('; ') || 'N/A'}
` : '';

      const response = await api.authFetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        // Case-law answers read full opinions — same budget as api.query.
        timeout: 180000,
        body: JSON.stringify({
          query: `You are a legal intelligence analyst. Answer the following question about this judge using ALL available data. Be thorough and cite specific cases/data points when relevant.

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
JUDGE PROFILE: ${judgeIntelProfile.name}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

BIOGRAPHICAL:
- Born: ${judgeIntelProfile.date_of_birth || 'Unknown'} in ${judgeIntelProfile.place_of_birth_city || ''}${judgeIntelProfile.place_of_birth_state ? ', ' + judgeIntelProfile.place_of_birth_state : ''}
- Gender: ${judgeIntelProfile.gender || 'Unknown'}
- Political Affiliation: ${judgeIntelProfile.political_affiliation || 'Unknown'}

EDUCATION:
${education}

CAREER/POSITIONS:
${positions}
${wikiContext}
${docketContext}
STATISTICS:
- Total Opinions: ${judgeIntelProfile.opinion_stats?.total_opinions || 0}
- Total Citations: ${judgeIntelProfile.opinion_stats?.total_citations || 0}
- Total Assigned Cases: ${judgeIntelProfile.docket_stats?.total_dockets || 0}
- Career Span: ${judgeIntelProfile.opinion_stats?.first_opinion || '?'} to ${judgeIntelProfile.opinion_stats?.last_opinion || '?'}
- Courts: ${courtBreakdown}
- Yearly Activity: ${yearlyTrend}

TOP 20 MOST-CITED OPINIONS:
${topCases}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
USER QUESTION: ${userQuery}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Provide a thorough, well-reasoned answer based on the judge data above.${judgeQueryIncludeDocs ? ' Also incorporate any relevant information from the user\'s document knowledge base.' : ''} If the question requires information not available in this data, say so but provide what analysis you can.`,
          mode: 'research',
          include_documents: judgeQueryIncludeDocs,
          include_case_law: false,
          document_filter: judgeQueryIncludeDocs ? judgeDocFilter : null,
        }),
      });
      if (!response.ok) throw new Error('Query failed');
      const data = await response.json();
      const assistantMsg: JudgeMessage = { id: Date.now() + 1, type: 'assistant', content: data.content };
      set((state) => ({ judgeMessages: [...state.judgeMessages, assistantMsg] }));
      persistJudgeSession();
    } catch (error: unknown) {
      const errorMsg: JudgeMessage = { id: Date.now() + 1, type: 'assistant', content: `Error: ${error instanceof Error ? error.message : String(error)}` };
      set((state) => ({ judgeMessages: [...state.judgeMessages, errorMsg] }));
    }
    set({ judgeQueryLoading: false });
  },

  queryJudgeOpinions: async (judgeId, query = '', offset = 0, sort) => {
    const order = sort ?? get().judgeIntelOpinionSort;
    set({ judgeIntelOpinionSort: order, judgeIntelOpinionsLoading: true });
    try {
      const apiOrder = order === 'citations' ? 'citations' : 'date';
      let url = `${API_BASE_URL}/judge-intel/profile/${judgeId}/opinions?limit=50&offset=${offset}&order=${apiOrder}`;
      if (query) url += `&q=${encodeURIComponent(query)}`;

      const response = await api.authFetch(url);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(formatErrorDetail(errorData.detail, 'Could not load opinions'));
      }
      const data = await response.json();

      const { judgeIntelOpinions } = get();
      if (offset > 0 && judgeIntelOpinions?.opinions) {
        set({
          judgeIntelOpinions: {
            ...data,
            opinions: [...judgeIntelOpinions.opinions, ...data.opinions],
          },
        });
      } else {
        set({ judgeIntelOpinions: data });
      }
    } catch (error: unknown) {
      logger.error('Opinions query error:', error);
      useUIStore.getState().addToast(error instanceof Error ? error.message : 'Could not load opinions', 'error');
    }
    set({ judgeIntelOpinionsLoading: false });
  },

  loadOpinionFullText: async (judgeId, opinionId) => {
    try {
      const response = await api.authFetch(`${API_BASE_URL}/judge-intel/profile/${judgeId}/opinion/${opinionId}`);
      if (response.ok) {
        const data = await response.json();
        set({ selectedOpinion: data });
      } else {
        const errorData = await response.json().catch(() => ({}));
        useUIStore.getState().addToast(formatErrorDetail(errorData.detail, 'Could not load that opinion'), 'error');
      }
    } catch (error: unknown) {
      logger.error('Opinion load error:', error);
      useUIStore.getState().addToast('Could not load that opinion', 'error');
    }
  },

  restoreWorkspaceSession: async (payload) => {
    const p = payload as {
      judgeId?: string | number;
      judgeName?: string;
      judgeMessages?: JudgeMessage[];
      judgeBrief?: string | null;
    };
    if (!p.judgeId) return;
    // The profile rebuilds from the local judge cache (instant when cached);
    // then the saved conversation and brief drop back in on top.
    await get().buildJudgeIntel(p.judgeId, p.judgeName || '');
    set({
      judgeMessages: Array.isArray(p.judgeMessages) ? p.judgeMessages : [],
      judgeBrief: p.judgeBrief ?? null,
    });
  },
});
});

registerReset(() => useJudgeIntelStore.setState(useJudgeIntelStore.getInitialState(), true));
