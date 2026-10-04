import { create } from 'zustand';
import { api, API_BASE_URL } from '../api';
import { formatErrorDetail } from '../api/client';
import { persistWorkspaceSession, resetWorkspaceSessionKey } from './workspaceSessionsStore';
import { registerReset } from './resetRegistry';
import { appNavigate, appNavigateBack } from '../utils/router';
import logger from '../utils/logger';
import { conversationTitle, downloadConversation } from '../utils/conversationExport';
import type { ConversationExportFormat } from '../api/types';
import type { CaseInfo, CaseMessage, DocumentFilter } from '../types';

export interface CaseViewState {
  mainViewCase: CaseInfo | null;
  caseLoading: boolean;
  setCaseLoading: (val: boolean) => void;
  caseMessages: CaseMessage[];
  caseQueryInput: string;
  setCaseQueryInput: (val: string) => void;
  caseQueryLoading: boolean;
  caseQueryIncludeDocs: boolean;
  setCaseQueryIncludeDocs: (val: boolean) => void;
  caseDocFilter: DocumentFilter | null;
  setCaseDocFilter: (val: DocumentFilter | null) => void;
  showCaseDocSelector: boolean;
  setShowCaseDocSelector: (val: boolean) => void;
  loadCaseDetail: (opinionId: string | number) => Promise<void>;
  initCaseFromRoute: (opinionId: string) => Promise<void>;
  queryCaseContext: () => Promise<void>;
  clearCaseConversation: () => void;
  exportingCaseConversation: boolean;
  exportCaseConversation: (format: ConversationExportFormat) => Promise<void>;
  closeCaseView: () => void;
  /** Rebuild a case session (opinion page + conversation) from History. */
  restoreWorkspaceSession: (payload: Record<string, unknown>) => Promise<void>;
}

export const useCaseViewStore = create<CaseViewState>((set, get) => ({
  mainViewCase: null,
  caseLoading: false,
  setCaseLoading: (val) => set({ caseLoading: val }),
  caseMessages: [],
  caseQueryInput: '',
  setCaseQueryInput: (val) => set({ caseQueryInput: val }),
  caseQueryLoading: false,
  caseQueryIncludeDocs: false,
  setCaseQueryIncludeDocs: (val) => set({ caseQueryIncludeDocs: val }),
  caseDocFilter: null,
  setCaseDocFilter: (val) => set({ caseDocFilter: val }),
  showCaseDocSelector: false,
  setShowCaseDocSelector: (val) => set({ showCaseDocSelector: val }),

  loadCaseDetail: async (opinionId) => {
    appNavigate(`/case/${opinionId}`);
    await get().initCaseFromRoute(String(opinionId));
  },

  // Route-driven load: lets /case/:id fetch itself on refresh or direct
  // navigation, where nothing has called loadCaseDetail.
  initCaseFromRoute: async (opinionId) => {
    const { caseLoading, mainViewCase } = get();
    if (caseLoading) return;
    if (mainViewCase && !mainViewCase.error && String(mainViewCase.id) === opinionId) return;
    // A different case is a new History session.
    resetWorkspaceSessionKey('case');
    set({ caseLoading: true, mainViewCase: null, caseMessages: [] });
    try {
      const response = await api.authFetch(`${API_BASE_URL}/tools/cases/${opinionId}`);
      if (!response.ok) throw new Error('Failed to load case');
      const data = await response.json();
      // Stamp the route id so the same-case guard above holds even if the
      // API payload omits or renames its own id field.
      set({ mainViewCase: { ...data, id: String(data.id ?? opinionId) } });
    } catch (error: unknown) {
      logger.error('Case detail error:', error);
      set({ mainViewCase: { error: (error as Error).message } as CaseInfo });
    }
    set({ caseLoading: false });
  },

  queryCaseContext: async () => {
    const { caseQueryInput, mainViewCase, caseQueryIncludeDocs, caseDocFilter } = get();
    if (!caseQueryInput.trim() || !mainViewCase) return;
    const userQuery = caseQueryInput.trim();
    set({ caseQueryInput: '', caseQueryLoading: true });

    const userMsg: CaseMessage = { id: Date.now(), type: 'user', content: userQuery };
    set((state) => ({ caseMessages: [...state.caseMessages, userMsg] }));

    try {
      const response = await api.authFetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        // Case-law answers read full opinions — same budget as api.query.
        timeout: 180000,
        body: JSON.stringify({
          query: caseQueryIncludeDocs
            ? `Based on this case AND any relevant documents from my knowledge base, answer the following question:

Case: ${mainViewCase.case_name}
Court: ${mainViewCase.court || 'Unknown'}
Date: ${mainViewCase.date_filed || 'Unknown'}

${mainViewCase.syllabus ? `Syllabus: ${mainViewCase.syllabus}` : ''}
${mainViewCase.opinion_text ? `Opinion: ${mainViewCase.opinion_text.substring(0, 10000)}` : ''}

Question: ${userQuery}

Please reference both the case above and any relevant documents from my knowledge base in your answer.`
            : `Based on this case, answer the following question:

Case: ${mainViewCase.case_name}
Court: ${mainViewCase.court || 'Unknown'}
Date: ${mainViewCase.date_filed || 'Unknown'}

${mainViewCase.syllabus ? `Syllabus: ${mainViewCase.syllabus}` : ''}
${mainViewCase.opinion_text ? `Opinion: ${mainViewCase.opinion_text.substring(0, 15000)}` : ''}

Question: ${userQuery}`,
          mode: 'research',
          include_documents: caseQueryIncludeDocs,
          include_case_law: false,
          document_filter: caseQueryIncludeDocs ? caseDocFilter : null,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(formatErrorDetail(errorData.detail, 'Query failed. Please check that you have entered an API key in Settings.'));
      }
      const data = await response.json();
      const assistantMsg: CaseMessage = { id: Date.now() + 1, type: 'assistant', content: data.content };
      set((state) => ({ caseMessages: [...state.caseMessages, assistantMsg] }));
      {
        const { mainViewCase: mc, caseMessages } = get();
        if (mc?.id) {
          persistWorkspaceSession('case', 'case', mc.case_name || `Case ${mc.id}`, {
            caseId: mc.id,
            caseName: mc.case_name || '',
            caseMessages,
          });
        }
      }
    } catch (error: unknown) {
      const msg = (error as Error).message || 'Something went wrong.';
      // Only suggest the API key when the failure actually looks key/auth
      // related — otherwise this misdirects (e.g. a validation 422).
      const looksLikeKey = /api key|unauthorized|\b401\b|no key|provider|invalid_api_key/i.test(msg);
      const hint = looksLikeKey ? '\n\nPlease ensure you have entered an API key in Settings.' : '';
      const errorMsg: CaseMessage = { id: Date.now() + 1, type: 'assistant', content: `Error: ${msg}${hint}` };
      set((state) => ({ caseMessages: [...state.caseMessages, errorMsg] }));
    }
    set({ caseQueryLoading: false });
  },

  exportingCaseConversation: false,
  exportCaseConversation: async (format) => {
    const { caseMessages, exportingCaseConversation, mainViewCase } = get();
    if (exportingCaseConversation) return;
    const firstQuestion = caseMessages.find((m) => m.type === 'user')?.content;
    const title = conversationTitle(mainViewCase?.case_name ? `${mainViewCase.case_name}` : 'Case conversation', firstQuestion);
    set({ exportingCaseConversation: true });
    try {
      await downloadConversation(
        title,
        caseMessages.map((m) => ({ role: m.type, text: m.content })),
        format,
      );
    } finally {
      set({ exportingCaseConversation: false });
    }
  },
  clearCaseConversation: () => {
    set({ caseMessages: [], caseQueryInput: '', caseQueryLoading: false });
  },

  restoreWorkspaceSession: async (payload) => {
    const p = payload as { caseId?: string | number; caseMessages?: CaseMessage[] };
    if (!p.caseId) return;
    appNavigate(`/case/${p.caseId}`);
    await get().initCaseFromRoute(String(p.caseId));
    set({ caseMessages: Array.isArray(p.caseMessages) ? p.caseMessages : [] });
  },

  closeCaseView: () => {
    set({ mainViewCase: null, caseMessages: [], caseQueryInput: '', caseLoading: false });
    // Back means BACK — to the search results that opened this case, with
    // their state intact — never a jump to the main screen.
    appNavigateBack();
  },
}));

registerReset(() => useCaseViewStore.setState(useCaseViewStore.getInitialState(), true));
