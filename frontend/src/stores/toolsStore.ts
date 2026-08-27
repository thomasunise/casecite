import { create } from 'zustand';
import { registerReset } from './resetRegistry';
import { conversationTitle, downloadConversation } from '../utils/conversationExport';
import type { ConversationExportFormat } from '../api/types';
import { api, API_BASE_URL } from '../api';
import { persistWorkspaceSession, resetWorkspaceSessionKey } from './workspaceSessionsStore';
import logger from '../utils/logger';

export interface ToolDefinition {
  id: string;
  name?: string;
  title?: string;
  placeholder?: string;
  description?: string;
  icon?: string;
  [key: string]: unknown;
}

export interface ToolChatMessage {
  id: number;
  type: 'user' | 'assistant';
  content: string;
}

// Build a compact, LLM-friendly summary of a tool's results so the
// "chat about these results" box can ground its answers in the data.
function summarizeToolResult(
  toolId: string,
  toolInput: string,
  r: Record<string, unknown> | null,
): string {
  if (!r) return '';
  const lines: string[] = [];
  const list = (arr: unknown[], fmt: (x: Record<string, unknown>) => string, max = 25) =>
    arr.slice(0, max).map((x, i) => `${i + 1}. ${fmt(x as Record<string, unknown>)}`).join('\n');
  const snip = (x: Record<string, unknown>) => (x.snippet ? ` — "${String(x.snippet).slice(0, 220)}"` : '');
  switch (toolId) {
    case 'case-lookup':
      if (Array.isArray(r.results)) lines.push(list(r.results, (c) => `${c.case_name} — ${Array.isArray(c.citation) ? (c.citation as string[])[0] || '' : ''} (${c.court || ''}, ${c.date_filed || ''})${snip(c)}`));
      break;
    case 'validate-citation':
      lines.push(`Citation: ${r.citation || toolInput}${r.case_name ? ` (${r.case_name})` : ''}`);
      if (r.warning_level) lines.push(`Treatment signal: ${r.warning_level}`);
      if (typeof r.total_citing_cases === 'number') lines.push(`Total citing cases: ${r.total_citing_cases}`);
      if (typeof r.positive_citations === 'number') lines.push(`Positive: ${r.positive_citations}, Caution: ${r.caution_citations ?? 0}, Negative: ${r.negative_citations}`);
      if (Array.isArray(r.citing_cases) && r.citing_cases.length) {
        lines.push('Citing opinions with treatment language:');
        lines.push(list(r.citing_cases, (c) => `${c.case_name} (${c.court || ''}, ${c.date_filed || ''}) — ${c.treatment}${snip(c)}`));
      }
      if (Array.isArray(r.notes)) lines.push(...(r.notes as string[]));
      break;
    case 'precedents':
      if (Array.isArray(r.precedents)) lines.push(list(r.precedents, (p) => `${p.case_name} — ${p.citation} (${p.court || ''}, ${p.date_filed || ''}; ${p.citation_count || p.times_cited || 0} citations)${snip(p)}`));
      break;
    case 'dockets':
      if (Array.isArray(r.dockets)) lines.push(list(r.dockets, (d) => `${d.case_name} — ${d.court} (${d.docket_number}${d.date_filed ? `, filed ${d.date_filed}` : ''})${d.nature_of_suit ? ` — ${d.nature_of_suit}` : ''}${d.assigned_to ? ` — Judge ${d.assigned_to}` : ''}`));
      break;
    case 'oral-arguments':
      if (Array.isArray(r.arguments)) lines.push(list(r.arguments, (a) => `${a.case_name} — ${a.court} (argued ${a.date_argued}${a.duration_label ? `, ${a.duration_label}` : ''})${a.judges ? ` — panel: ${a.judges}` : ''}${snip(a)}`));
      break;
    case 'trends':
      if (Array.isArray(r.years)) lines.push(`Yearly case counts for "${toolInput}": ` + (r.years as Record<string, unknown>[]).map((y) => `${y.year}: ${y.count}`).join(', ') + (r.trend ? ` (trend: ${r.trend}${r.current_year_partial ? '; current year partial' : ''})` : ''));
      break;
  }
  return lines.join('\n');
}

export interface ToolsState {
  activeTool: ToolDefinition | null;
  setActiveTool: (val: ToolDefinition | null) => void;
  toolLoading: boolean;
  toolApiSlow: boolean;
  toolResult: Record<string, unknown> | null;
  setToolResult: (val: Record<string, unknown> | null) => void;
  toolInput: string;
  setToolInput: (val: string) => void;
  nextCursor: string | null;
  selectedCase: Record<string, unknown> | null;
  setSelectedCase: (val: Record<string, unknown> | null) => void;
  caseLoading: boolean;
  setCaseLoading: (val: boolean) => void;
  // Open a precedent's full opinion one level deep in the tools area
  // (Back to results returns to the list) — no navigation away.
  loadPrecedentCase: (id: number | string) => Promise<void>;
  selectedJudge: string | null;
  setSelectedJudge: (val: string | null) => void;
  // In-app docket viewer (metadata + filing entries + parties)
  selectedDocket: Record<string, unknown> | null;
  setSelectedDocket: (val: Record<string, unknown> | null) => void;
  docketLoading: boolean;
  loadDocketDetail: (docketId: number) => Promise<void>;
  handleToolSearch: (loadMore?: boolean) => Promise<void>;
  loadMoreResults: () => void;
  // Open a tool in the center view, resetting any prior tool state.
  openTool: (tool: ToolDefinition) => void;
  // Center-view "chat about these results"
  toolChatMessages: ToolChatMessage[];
  toolChatInput: string;
  setToolChatInput: (val: string) => void;
  toolChatLoading: boolean;
  sendToolChat: () => Promise<void>;
  clearToolChat: () => void;
  exportingToolChat: boolean;
  exportToolChat: (format: ConversationExportFormat) => Promise<void>;
  /** Rebuild a tool session (search + results + chat) from History. */
  restoreWorkspaceSession: (toolId: string, payload: Record<string, unknown>) => void;
}

export const useToolsStore = create<ToolsState>((set, get) => {
let toolSlowTimer: ReturnType<typeof setTimeout> | null = null;

// Universal History: one session per tool run — the search, its results, and
// the result-chat all snapshot together so History rebuilds the whole page.
const persistToolSession = () => {
  const { activeTool, toolInput, toolResult, toolChatMessages } = get();
  if (!activeTool || !toolResult || (toolResult as { error?: string }).error) return;
  persistWorkspaceSession(
    `tool:${activeTool.id}`,
    `tool:${activeTool.id}`,
    `${activeTool.name || activeTool.id}: ${toolInput.slice(0, 80)}`,
    { tool: activeTool, toolInput, toolResult, toolChatMessages },
  );
};

registerReset(() => {
  if (toolSlowTimer) { clearTimeout(toolSlowTimer); toolSlowTimer = null; }
  useToolsStore.setState(useToolsStore.getInitialState(), true);
});

return ({
  activeTool: null,
  setActiveTool: (val) => set({ activeTool: val }),
  toolLoading: false,
  toolApiSlow: false,
  toolResult: null,
  setToolResult: (val) => set({ toolResult: val }),
  toolInput: '',
  setToolInput: (val) => set({ toolInput: val }),
  nextCursor: null,
  selectedCase: null,
  setSelectedCase: (val) => set({ selectedCase: val }),
  caseLoading: false,
  setCaseLoading: (val) => set({ caseLoading: val }),

  loadPrecedentCase: async (id) => {
    set({ caseLoading: true, selectedCase: null });
    try {
      const response = await api.authFetch(`${API_BASE_URL}/tools/cases/${id}`, {
        method: 'GET', headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to load case');
      }
      set({ selectedCase: await response.json() });
    } catch (error: unknown) {
      logger.error('Precedent case error:', error);
      set({ selectedCase: { error: error instanceof Error ? error.message : 'Failed to load case' } });
    }
    set({ caseLoading: false });
  },

  selectedJudge: null,
  setSelectedJudge: (val) => set({ selectedJudge: val }),
  selectedDocket: null,
  setSelectedDocket: (val) => set({ selectedDocket: val }),
  docketLoading: false,

  loadDocketDetail: async (docketId) => {
    set({ docketLoading: true, selectedDocket: null });
    try {
      const response = await api.authFetch(`${API_BASE_URL}/tools/dockets/${docketId}`, {
        method: 'GET', headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to load docket');
      }
      set({ selectedDocket: await response.json() });
    } catch (error: unknown) {
      logger.error('Docket detail error:', error);
      set({ selectedDocket: { error: error instanceof Error ? error.message : 'Failed to load docket' } });
    }
    set({ docketLoading: false });
  },

  handleToolSearch: async (loadMore = false) => {
    const { activeTool, toolInput, toolResult, nextCursor } = get();
    if (!activeTool || !toolInput.trim()) return;

    set({ toolLoading: true, toolApiSlow: false });
    if (toolSlowTimer) clearTimeout(toolSlowTimer);
    toolSlowTimer = setTimeout(() => set({ toolApiSlow: true }), 10000);

    if (!loadMore) {
      set({ toolResult: null, selectedCase: null, nextCursor: null, selectedJudge: null, selectedDocket: null, toolChatMessages: [], toolChatInput: '' });
      // A fresh search is a fresh History session for this tool.
      resetWorkspaceSessionKey(`tool:${activeTool.id}`);
    }

    try {
      let endpoint;
      switch (activeTool.id) {
        case 'case-lookup':
          endpoint = loadMore && nextCursor ? null : `/tools/cases/search?q=${encodeURIComponent(toolInput)}&page_size=25`;
          break;
        case 'validate-citation':
          endpoint = `/tools/validate-citation?citation=${encodeURIComponent(toolInput)}`;
          break;
        case 'precedents':
          endpoint = `/tools/precedents?topic=${encodeURIComponent(toolInput)}&limit=50`;
          break;
        case 'dockets':
          endpoint = `/tools/dockets?query=${encodeURIComponent(toolInput)}&limit=50`;
          break;
        case 'oral-arguments':
          endpoint = `/tools/oral-arguments?query=${encodeURIComponent(toolInput)}&limit=50`;
          break;
        case 'trends':
          endpoint = `/tools/trends?topic=${encodeURIComponent(toolInput)}&start_year=2000`;
          break;
        default:
          throw new Error('Unknown tool');
      }

      let response;
      if (activeTool.id === 'case-lookup' && loadMore && nextCursor) {
        response = await api.authFetch(`${API_BASE_URL}/tools/cases/search?q=${encodeURIComponent(toolInput)}&cursor=${encodeURIComponent(nextCursor)}&page_size=25`, {
          method: 'GET', headers: { 'Content-Type': 'application/json' },
        });
      } else {
        response = await api.authFetch(`${API_BASE_URL}${endpoint}`, {
          method: 'GET', headers: { 'Content-Type': 'application/json' },
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed: ${response.status}`);
      }

      const data = await response.json();

      if (activeTool.id === 'case-lookup' && loadMore && toolResult?.results) {
        set({
          toolResult: { ...data, results: [...(toolResult.results as unknown[]), ...(data.results as unknown[])] },
        });
      } else {
        set({ toolResult: data });
      }

      if (data.next_cursor) set({ nextCursor: data.next_cursor });
      persistToolSession();
    } catch (error: unknown) {
      logger.error('Tool search error:', error);
      set({ toolResult: { error: error instanceof Error ? error.message : 'Search failed' } });
    }

    if (toolSlowTimer) { clearTimeout(toolSlowTimer); toolSlowTimer = null; }
    set({ toolApiSlow: false, toolLoading: false });
  },

  loadMoreResults: () => {
    const { toolResult, toolLoading, handleToolSearch } = get();
    if (toolResult?.has_next && !toolLoading) handleToolSearch(true);
  },

  openTool: (tool) => set({
    activeTool: tool,
    toolInput: '',
    toolResult: null,
    nextCursor: null,
    selectedCase: null,
    selectedJudge: null,
    selectedDocket: null,
    docketLoading: false,
    toolChatMessages: [],
    toolChatInput: '',
    toolChatLoading: false,
  }),

  toolChatMessages: [],
  toolChatInput: '',
  setToolChatInput: (val) => set({ toolChatInput: val }),
  toolChatLoading: false,

  clearToolChat: () => set({ toolChatMessages: [], toolChatInput: '', toolChatLoading: false }),
  exportingToolChat: false,
  exportToolChat: async (format) => {
    const { toolChatMessages, exportingToolChat, activeTool } = get();
    if (exportingToolChat) return;
    const firstQuestion = toolChatMessages.find((m) => m.type === 'user')?.content;
    const title = conversationTitle(activeTool ? `${activeTool.name} results` : 'Tool results', firstQuestion);
    set({ exportingToolChat: true });
    try {
      await downloadConversation(
        title,
        toolChatMessages.map((m) => ({ role: m.type, text: m.content })),
        format,
      );
    } finally {
      set({ exportingToolChat: false });
    }
  },

  restoreWorkspaceSession: (toolId, payload) => {
    const p = payload as {
      tool?: ToolDefinition;
      toolInput?: string;
      toolResult?: Record<string, unknown>;
      toolChatMessages?: ToolChatMessage[];
    };
    set({
      activeTool: p.tool || { id: toolId },
      toolInput: p.toolInput || '',
      toolResult: p.toolResult || null,
      toolChatMessages: Array.isArray(p.toolChatMessages) ? p.toolChatMessages : [],
      toolChatInput: '',
      toolChatLoading: false,
      toolLoading: false,
      toolApiSlow: false,
      selectedCase: null,
      selectedJudge: null,
      selectedDocket: null,
      docketLoading: false,
      nextCursor: (p.toolResult?.next_cursor as string) || null,
    });
  },

  sendToolChat: async () => {
    const { toolChatInput, activeTool, toolResult, toolInput } = get();
    if (!toolChatInput.trim() || !activeTool || !toolResult) return;
    const userQuery = toolChatInput.trim();
    set({ toolChatInput: '', toolChatLoading: true });
    set((state) => ({
      toolChatMessages: [...state.toolChatMessages, { id: Date.now(), type: 'user', content: userQuery }],
    }));
    try {
      const context = summarizeToolResult(activeTool.id, toolInput, toolResult);
      const response = await api.authFetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(api.getToken() && { Authorization: `Bearer ${api.getToken()}` }),
        },
        body: JSON.stringify({
          query: `Using these ${activeTool.name || 'legal search'} results for "${toolInput}", answer the question.

Results:
${context}

Question: ${userQuery}`,
          mode: 'research',
          include_documents: false,
          include_case_law: false,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Chat failed. Please check that you have entered an API key in Settings.');
      }
      const data = await response.json();
      set((state) => ({
        toolChatMessages: [...state.toolChatMessages, { id: Date.now() + 1, type: 'assistant', content: data.content }],
      }));
      persistToolSession();
    } catch (error: unknown) {
      set((state) => ({
        toolChatMessages: [...state.toolChatMessages, { id: Date.now() + 1, type: 'assistant', content: `Error: ${(error as Error).message}` }],
      }));
    }
    set({ toolChatLoading: false });
  },
});
});
