import { create } from 'zustand';
import { api } from '../api';
import type {
  ContractAnalysisListItem,
  ContractAnalysisResult,
  ContractChatCitation,
  ContractComparison,
  ContractComparisonSet,
  ContractDraft,
  ContractJobResult,
  ContractRedlineEdit,
} from '../api/types';
import { useUIStore } from './uiStore';
import { persistWorkspaceSession, resetWorkspaceSessionKey } from './workspaceSessionsStore';
import { registerReset } from './resetRegistry';
import { downloadBlob } from '../utils/downloadBlob';
import { fetchDocumentPdfUrl } from '../utils/documentFile';
import logger from '../utils/logger';
import { conversationTitle, downloadConversation } from '../utils/conversationExport';
import type { ConversationExportFormat, ConversationExportMessage } from '../api/types';

export interface ContractChatMessage {
  id: string;
  role: 'user' | 'assistant';
  kind: 'text' | 'analysis' | 'answer' | 'redlines' | 'draft' | 'comparison' | 'comparison_set' | 'clarify';
  /** clarify: quick-answer options; clicking one re-sends with the goal attached. */
  options?: string[];
  originalMessage?: string;
  text?: string;
  analysis?: ContractAnalysisResult;
  citations?: ContractChatCitation[];
  redlines?: ContractRedlineEdit[];
  draft?: ContractDraft;
  comparison?: ContractComparison;
  comparisonSet?: ContractComparisonSet;
  /** The stored analysis behind a redlines message — needed for export. */
  analysisId?: string;
}

/** Flatten a contract message (structured kinds included) into export text. */
function contractMessageToExport(msg: ContractChatMessage): ConversationExportMessage {
  if (msg.role === 'user') return { role: 'user', text: msg.text || '' };
  const parts: string[] = [];
  if (msg.text) parts.push(msg.text);
  if (msg.analysis) {
    const a = msg.analysis;
    if (a.executive_summary) parts.push(a.executive_summary);
    if (a.issues?.length) {
      parts.push('## Issues');
      for (const i of a.issues) parts.push(`- ${i.title}${i.why ? ` — ${i.why}` : ''}`);
    }
  }
  if (msg.redlines?.length) {
    parts.push('## Proposed redlines');
    for (const e of msg.redlines) {
      parts.push(`### ${e.title}`);
      if (e.original_text) parts.push(`Original: ${e.original_text}`);
      parts.push(`Proposed: ${e.proposed_text}`);
      if (e.rationale) parts.push(`Why: ${e.rationale}`);
    }
  }
  if (msg.draft) {
    parts.push(`## ${msg.draft.title || 'Draft'}`);
    parts.push(msg.draft.text);
  }
  const comparisons = msg.comparison ? [msg.comparison] : msg.comparisonSet?.comparisons || [];
  for (const c of comparisons) {
    parts.push(`## ${c.label_a} vs ${c.label_b}`);
    if (c.overall) parts.push(c.overall);
    for (const cl of c.clauses) parts.push(`- ${cl.topic} (${cl.status}): ${cl.summary}`);
  }
  if (msg.kind === 'clarify' && msg.options?.length) {
    parts.push(`Options offered: ${msg.options.join(' / ')}`);
  }
  return {
    role: 'assistant',
    text: parts.join('\n\n'),
    citations: (msg.citations || []).map((c, i) => ({ label: `Quote ${i + 1}`, quote: c.quote })),
  };
}

export type RedlineDecision = 'accepted' | 'rejected';

export interface ContractsState {
  selectedDocumentId: string;
  messages: ContractChatMessage[];
  sending: boolean;
  analyzing: boolean;
  progressMessage: string;
  analyses: ContractAnalysisListItem[];
  analysesLoading: boolean;
  openingAnalysisId: string | null;
  exporting: boolean;
  uploadingContract: boolean;
  viewerOpen: boolean;
  contractText: string | null;
  /** Object URL of the contract rendered as PDF (native formatting), when available. */
  contractFileUrl: string | null;
  contractTextLoading: boolean;
  /** Per-edit accept/reject, keyed `${analysisId}:${ref}`. Missing = accepted. */
  redlineDecisions: Record<string, RedlineDecision>;
  /** The user's own edits to proposed redline wording, keyed `${analysisId}:${ref}`. */
  redlineOverrides: Record<string, string>;
  setRedlineOverride: (analysisId: string, ref: string, text: string) => void;
  /** The user hand-edited the working copy of the contract text. */
  contractTextDirty: boolean;
  updateContractText: (text: string) => void;
  /** Download the hand-edited working copy as a Word file. */
  exportEditedContract: (filename: string) => Promise<void>;
  /** A request from the redlines panel to anchor an edit in the document. */
  pendingEditJump: { ref: string; seq: number } | null;
  requestEditJump: (ref: string) => void;
  /** The edit currently open in the document popover — highlighted everywhere. */
  activeEditRef: string | null;
  setActiveEditRef: (ref: string | null) => void;
  _initialized: boolean;
  setSelectedDocumentId: (id: string) => void;
  uploadContract: (file: File) => Promise<void>;
  toggleViewer: () => Promise<void>;
  loadContractText: () => Promise<void>;
  getViewerHighlights: () => string[];
  getActiveRedlines: () => { analysisId: string; edits: ContractRedlineEdit[] } | null;
  init: () => void;
  loadAnalyses: () => Promise<void>;
  /** Wipe the conversation and start fresh — document state stays. */
  clearConversation: () => void;
  /** Download the conversation (analyses, redlines and drafts included as text). */
  exportConversation: (format: ConversationExportFormat, filename?: string | null) => Promise<void>;
  /** Rebuild a full session from a History snapshot. */
  restoreWorkspaceSession: (payload: Record<string, unknown>) => Promise<void>;
  /** Auto-routed by default; 'redline' forces markup mode (the Redline chip). */
  sendMessage: (text: string, mode?: 'redline') => Promise<void>;
  openAnalysis: (id: string) => Promise<void>;
  exportAnalysis: (analysisId: string, format: 'docx' | 'md') => Promise<void>;
  setRedlineDecision: (analysisId: string, ref: string, decision: RedlineDecision) => void;
  exportRedlineDocx: (analysisId: string) => Promise<void>;
  exportDraftDocx: (title: string, text: string) => Promise<void>;
  /** Split view: 2-4 documents side by side, optionally with comparison
      highlights. Opened by multi-selecting files or by a finished compare. */
  comparisonView: {
    docs: Array<{ id: string; label: string; text: string }>;
    comparisons: ContractComparison[];
    loading: boolean;
  } | null;
  comparisonJump: { comparisonIndex: number; clauseIndex: number; seq: number } | null;
  /** Open 2-4 selected documents in split panes (no highlights yet). */
  openSplitDocs: (docs: Array<{ id: string; name: string }>) => Promise<void>;
  /** Open the split view from a finished comparison (loads the doc texts). */
  openComparisonView: (comparisons: ContractComparison[]) => Promise<void>;
  closeComparisonView: () => void;
  /** Compare every document currently open in the split view. */
  compareOpenDocs: (focus?: string) => Promise<void>;
  jumpToComparisonClause: (comparison: ContractComparison, clauseIndex: number) => Promise<void>;
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;

let messageSeq = 0;
function nextMessageId(): string {
  return `cmsg-${Date.now()}-${++messageSeq}`;
}

function toast(msg: string, type = 'info') {
  try { useUIStore.getState().addToast(msg, type); } catch { /* noop */ }
}

export const useContractsStore = create<ContractsState>((set, get) => {
  // Universal History: snapshot the whole working session (conversation,
  // selected doc, draft workspace, comparison) so History can rebuild it.
  const persistSession = () => {
    const st = get();
    if (st.messages.length === 0) return;
    const firstUserMsg = st.messages.find((m) => m.role === 'user')?.text;
    const title = firstUserMsg ? firstUserMsg.slice(0, 80) : 'Contract session';
    persistWorkspaceSession('contracts', 'contracts', title, {
      selectedDocumentId: st.selectedDocumentId || null,
      messages: st.messages,
      comparison: st.comparisonView
        ? {
            docs: st.comparisonView.docs.map((d) => ({ id: d.id, label: d.label })),
            comparisons: st.comparisonView.comparisons,
          }
        : null,
    });
  };

  const pushMessage = (msg: Omit<ContractChatMessage, 'id'>) => {
    set((st) => ({ messages: [...st.messages, { id: nextMessageId(), ...msg }] }));
    // Every settled result flows through here — one autosave hook covers all.
    if (msg.role === 'assistant') queueMicrotask(persistSession);
  };

  const failChat = (msg: string) => {
    set({ sending: false, analyzing: false, progressMessage: '' });
    pushMessage({ role: 'assistant', kind: 'text', text: msg });
    toast(msg, 'error');
  };

  const loadDocText = async (docId: string): Promise<string> => {
    try {
      const res = await api.getDocumentContent(docId);
      return res.text || '';
    } catch (e) {
      logger.error('split-view doc load failed', e);
      return '';
    }
  };

  // A completed job resolves to one of four result shapes; push the matching
  // assistant message. Plain analyses carry no `kind` discriminant.
  const settleJobResult = (result: ContractJobResult) => {
    if ('kind' in result) {
      if (result.kind === 'redlines') {
        try {
          useUIStore.getState().setRightPanelTab('sources');
          useUIStore.getState().setRightSidebarCollapsed(false);
        } catch { /* noop */ }
        pushMessage({
          role: 'assistant',
          kind: 'redlines',
          redlines: result.redlines,
          analysisId: result.analysis_id,
          // The basis the redline was drafted on — shown in the receipt so
          // the run is never a black box.
          text: (result.summary as { instructions?: string | null } | undefined)?.instructions || undefined,
        });
        get().loadAnalyses();
      } else if (result.kind === 'draft') {
        // Drafting lives in its own tab — a draft produced here (a message
        // that routed to drafting) opens there.
        pushMessage({
          role: 'assistant',
          kind: 'text',
          text: `Draft ready — "${result.title || 'Draft'}" opened in the Drafting tab.`,
        });
        void (async () => {
          try {
            const { useDraftingStore } = await import('./draftingStore');
            useDraftingStore.getState().receiveDraft(result);
            const { appNavigate } = await import('../utils/router');
            appNavigate('/drafting');
          } catch (e) {
            logger.error('draft handoff failed', e);
          }
        })();
      } else if (result.kind === 'draft_plan') {
        // Long-draft plans are polled by the Drafting workspace; a plan never
        // arrives through the Contracts chat.
        return;
      } else {
        const comparisons = result.kind === 'comparison_set' ? result.comparisons : [result];
        if (result.kind === 'comparison_set') {
          pushMessage({ role: 'assistant', kind: 'comparison_set', comparisonSet: result });
        } else {
          pushMessage({ role: 'assistant', kind: 'comparison', comparison: result });
        }
        // A finished comparison opens the split screen right away and lands
        // its findings in the Sources panel.
        try {
          useUIStore.getState().setRightPanelTab('sources');
          useUIStore.getState().setRightSidebarCollapsed(false);
        } catch { /* noop */ }
        const view = get().comparisonView;
        const viewIds = view ? view.docs.map((d) => d.id) : [];
        const neededIds = [
          comparisons[0]?.document_id_a,
          ...comparisons.map((c) => c.document_id_b),
        ].filter(Boolean);
        if (view && !view.loading && neededIds.every((id) => viewIds.includes(id!))) {
          // The docs are already open in panes — just drop the highlights in.
          set({ comparisonView: { ...view, comparisons } });
        } else {
          get().openComparisonView(comparisons);
        }
      }
      return;
    }
    pushMessage({ role: 'assistant', kind: 'analysis', analysis: result });
    get().loadAnalyses();
  };

  // Poll a contract job (analysis, redlines, draft, or comparison) until it
  // settles, then inject the result into the chat as an assistant message.
  const pollContractJob = (jobId: string) => {
    const poll = async (attempt: number) => {
      try {
        const job = await api.getContractJob(jobId);
        if (job.status === 'completed') {
          set({ analyzing: false, progressMessage: '' });
          if (job.result) {
            settleJobResult(job.result);
          } else {
            failChat('The job finished but returned no result.');
          }
          return;
        }
        if (job.status === 'failed' || job.status === 'cancelled') {
          failChat(job.error || 'Contract analysis failed.');
          return;
        }
        if (attempt > 150) {
          failChat('Timed out waiting for results.');
          return;
        }
        if (attempt === 30) {
          set({ progressMessage: 'Still working — long contracts can take a couple of minutes…' });
        }
        pollTimer = setTimeout(() => poll(attempt + 1), 2000);
      } catch (e) {
        failChat(e instanceof Error ? e.message : 'Polling failed.');
      }
    };
    poll(0);
  };

  return {
    selectedDocumentId: '',
    messages: [],
    sending: false,
    analyzing: false,
    progressMessage: '',
    analyses: [],
    analysesLoading: false,
    openingAnalysisId: null,
    exporting: false,
    uploadingContract: false,
    redlineDecisions: {},
    pendingEditJump: null,
    activeEditRef: null,

    setActiveEditRef: (ref) => set({ activeEditRef: ref }),

    requestEditJump: (ref) => {
      set((st) => ({
        pendingEditJump: { ref, seq: (st.pendingEditJump?.seq || 0) + 1 },
      }));
    },

    uploadContract: async (file) => {
      if (get().uploadingContract) return;
      const name = file.name.toLowerCase();
      const supported = ['.pdf', '.docx', '.doc', '.txt', '.rtf'];
      if (!supported.some((ext) => name.endsWith(ext))) {
        toast('Unsupported file type — upload a PDF, Word, or text document.', 'error');
        return;
      }
      set({ uploadingContract: true });
      try {
        const result = await api.uploadDocument(file);
        const docId = (result.document_id as string) || result.id;
        if (result.status === 'failed' || !docId) {
          const meta = result.metadata as Record<string, string> | undefined;
          toast(meta?.error || 'The document could not be indexed.', 'error');
          return;
        }
        // Refresh the indexed-docs list the selector reads, then select the
        // fresh upload so the chat unlocks immediately.
        const { useRagDocsStore } = await import('./ragDocsStore');
        await useRagDocsStore.getState().loadRagDocuments();
        get().setSelectedDocumentId(docId);
        toast(`${file.name} indexed — ask away.`, 'success');
      } catch (e) {
        logger.error('Contract upload failed:', e);
        toast(e instanceof Error ? e.message : 'Upload failed.', 'error');
      } finally {
        set({ uploadingContract: false });
      }
    },

    // Switching contracts starts a fresh conversation. Past analyses stay
    // global — they are not tied to the selected document.
    setSelectedDocumentId: (id) => {
      if (id === get().selectedDocumentId) return;
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      // Switching contracts starts a new session in History too.
      resetWorkspaceSessionKey('contracts');
      const prevUrl = get().contractFileUrl;
      if (prevUrl) URL.revokeObjectURL(prevUrl);
      set({
        selectedDocumentId: id,
        messages: [],
        sending: false,
        analyzing: false,
        progressMessage: '',
        contractText: null,
        contractFileUrl: null,
        contractTextDirty: false,
        viewerOpen: !!id,
      });
      // The contract is the centerpiece of the workspace — load its text as
      // soon as it is selected.
      if (id) void get().loadContractText();
    },

    loadContractText: async () => {
      const { selectedDocumentId } = get();
      if (!selectedDocumentId) return;
      set({ contractTextLoading: true });
      try {
        // Extracted text (chat/redline anchors) and the native file render
        // (real formatting) load together.
        const [content, fileUrl] = await Promise.all([
          api.getDocumentContent(selectedDocumentId),
          fetchDocumentPdfUrl(selectedDocumentId),
        ]);
        // The selection may have changed while loading — don't leak the URL.
        if (get().selectedDocumentId !== selectedDocumentId) {
          if (fileUrl) URL.revokeObjectURL(fileUrl);
          return;
        }
        set({ contractText: content.text || '', contractFileUrl: fileUrl, contractTextDirty: false });
      } catch (e) {
        logger.error('Failed to load contract text:', e);
        toast('Could not load the contract text.', 'error');
      } finally {
        set({ contractTextLoading: false });
      }
    },

    viewerOpen: false,
    contractText: null,
    contractFileUrl: null,
    contractTextLoading: false,
    contractTextDirty: false,

    updateContractText: (text) => {
      set({ contractText: text, contractTextDirty: true });
    },

    exportEditedContract: async (filename) => {
      const { contractText, exporting } = get();
      if (!contractText || exporting) return;
      set({ exporting: true });
      try {
        const title = filename.replace(/\.[^.]+$/, '') || 'Edited contract';
        const blob = await api.exportDraft(title, contractText);
        const safeName = title.trim().replace(/[^\w-]+/g, '-').replace(/^-+|-+$/g, '') || 'contract';
        downloadBlob(blob, `${safeName}-edited.docx`);
        toast('Edited copy downloaded.', 'success');
      } catch (e) {
        logger.error('edited contract export failed', e);
        toast(e instanceof Error ? e.message : 'Export failed.', 'error');
      } finally {
        set({ exporting: false });
      }
    },

    redlineOverrides: {},
    setRedlineOverride: (analysisId, ref, text) => {
      set((st) => ({
        redlineOverrides: { ...st.redlineOverrides, [`${analysisId}:${ref}`]: text },
      }));
    },

    toggleViewer: async () => {
      const { viewerOpen, contractText, selectedDocumentId } = get();
      if (viewerOpen) {
        set({ viewerOpen: false });
        return;
      }
      if (!selectedDocumentId) return;
      set({ viewerOpen: true });
      if (contractText === null) await get().loadContractText();
    },

    // The most recent redline set in this conversation — rendered inline in
    // the contract with the side rail.
    getActiveRedlines: () => {
      const { messages } = get();
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if (msg.role === 'assistant' && msg.kind === 'redlines' && msg.redlines?.length && msg.analysisId) {
          return { analysisId: msg.analysisId, edits: msg.redlines };
        }
      }
      return null;
    },

    // Quotes worth highlighting in the viewer: the most recent assistant
    // message's grounded material (answer citations, or an analysis's
    // verified key-term quotes + grounded issue text).
    getViewerHighlights: () => {
      const { messages } = get();
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if (msg.role !== 'assistant') continue;
        if (msg.kind === 'answer' && msg.citations?.length) {
          return msg.citations.map((c) => c.quote).filter(Boolean);
        }
        if (msg.kind === 'analysis' && msg.analysis) {
          const quotes: string[] = [];
          for (const term of Object.values(msg.analysis.key_terms || {})) {
            if (term.verified && term.quote) quotes.push(term.quote);
          }
          for (const issue of msg.analysis.issues || []) {
            if (issue.grounding === 'span' && issue.matched_text) quotes.push(issue.matched_text);
          }
          return quotes.slice(0, 40);
        }
      }
      return [];
    },

    _initialized: false,
    // Lazy first load, called from the view's useEffect.
    init: () => {
      if (get()._initialized) return;
      set({ _initialized: true });
      get().loadAnalyses();
    },

    loadAnalyses: async () => {
      set({ analysesLoading: true });
      try {
        const resp = await api.listContractAnalyses();
        set({ analyses: resp.analyses || [] });
      } catch (e) {
        logger.error('Failed to load contract analyses:', e);
        // An empty list with no explanation reads as "no analyses yet".
        toast('Could not load past analyses.', 'error');
      } finally {
        set({ analysesLoading: false });
      }
    },

    sendMessage: async (text, mode) => {
      const trimmed = text.trim();
      const { selectedDocumentId, sending, analyzing } = get();
      if (!trimmed || sending || analyzing) return;
      if (!selectedDocumentId) {
        toast('Select a contract to chat about first.', 'error');
        return;
      }
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      pushMessage({ role: 'user', kind: 'text', text: trimmed });
      set({ sending: true });

      try {
        // Auto-routed by default (ask / review / draft); the Redline chip
        // forces markup mode explicitly.
        const resp = await api.contractChat(selectedDocumentId, trimmed, mode);
        if (resp.type === 'analysis_started') {
          set({
            sending: false,
            analyzing: true,
            progressMessage: 'Reading the contract — extracting parties, terms, obligations, and risks…',
          });
          pollContractJob(resp.job_id);
        } else if (resp.type === 'redline_started') {
          set({
            sending: false,
            analyzing: true,
            progressMessage: 'Preparing redlines — reviewing the contract and proposing tracked edits…',
          });
          pollContractJob(resp.job_id);
        } else if (resp.type === 'draft_started') {
          set({
            sending: false,
            analyzing: true,
            progressMessage: 'Drafting — building the document from your instructions…',
          });
          pollContractJob(resp.job_id);
        } else if (resp.type === 'clarify') {
          // The engine refuses to guess the goal — surface its question with
          // one-click answers that re-send the request with the goal attached.
          set({ sending: false });
          pushMessage({
            role: 'assistant',
            kind: 'clarify',
            text: resp.question,
            options: resp.options,
            originalMessage: text,
          });
        } else {
          set({ sending: false });
          pushMessage({
            role: 'assistant',
            kind: 'answer',
            text: resp.answer,
            citations: resp.citations || [],
          });
        }
      } catch (e) {
        logger.error('contract chat failed', e);
        failChat(e instanceof Error ? e.message : 'Failed to send message.');
      }
    },

    // Opening a past analysis injects it into the chat as an assistant message.
    openAnalysis: async (id) => {
      if (get().openingAnalysisId) return;
      set({ openingAnalysisId: id });
      try {
        const result = await api.getContractAnalysis(id);
        pushMessage({ role: 'assistant', kind: 'analysis', analysis: result });
      } catch (e) {
        logger.error('open contract analysis failed', e);
        toast('Failed to load that analysis.', 'error');
      } finally {
        set({ openingAnalysisId: null });
      }
    },

    exportAnalysis: async (analysisId, format) => {
      if (!analysisId || get().exporting) return;
      set({ exporting: true });
      try {
        const blob = await api.exportContractAnalysis(analysisId, format);
        downloadBlob(blob, `contract-analysis-${analysisId}.${format === 'docx' ? 'docx' : 'md'}`);
        toast('Export downloaded.', 'success');
      } catch (e) {
        logger.error('contract analysis export failed', e);
        toast(e instanceof Error ? e.message : 'Export failed.', 'error');
      } finally {
        set({ exporting: false });
      }
    },

    setRedlineDecision: (analysisId, ref, decision) => {
      set((st) => ({
        redlineDecisions: { ...st.redlineDecisions, [`${analysisId}:${ref}`]: decision },
      }));
    },

    // Export accepted edits as a tracked-changes Word file. The backend takes
    // the REJECTED refs via `exclude`; everything else is included.
    exportRedlineDocx: async (analysisId) => {
      if (!analysisId || get().exporting) return;
      const prefix = `${analysisId}:`;
      const rejected = Object.entries(get().redlineDecisions)
        .filter(([key, decision]) => decision === 'rejected' && key.startsWith(prefix))
        .map(([key]) => key.slice(prefix.length));
      const overrides: Record<string, string> = {};
      for (const [key, text] of Object.entries(get().redlineOverrides)) {
        if (key.startsWith(prefix)) overrides[key.slice(prefix.length)] = text;
      }
      set({ exporting: true });
      try {
        const blob = await api.exportRedlines(analysisId, rejected, overrides);
        downloadBlob(blob, `contract-redlines-${analysisId}.docx`);
        toast('Tracked-changes document downloaded.', 'success');
      } catch (e) {
        logger.error('redline export failed', e);
        toast(e instanceof Error ? e.message : 'Redline export failed.', 'error');
      } finally {
        set({ exporting: false });
      }
    },

    exportDraftDocx: async (title, text) => {
      if (get().exporting) return;
      set({ exporting: true });
      try {
        const blob = await api.exportDraft(title, text);
        const safeName = title.trim().replace(/[^\w-]+/g, '-').replace(/^-+|-+$/g, '') || 'draft';
        downloadBlob(blob, `${safeName}.docx`);
        toast('Draft downloaded.', 'success');
      } catch (e) {
        logger.error('draft export failed', e);
        toast(e instanceof Error ? e.message : 'Draft export failed.', 'error');
      } finally {
        set({ exporting: false });
      }
    },

    exportConversation: async (format, filename) => {
      const { messages, exporting } = get();
      if (exporting) return;
      const firstQuestion = messages.find((m) => m.role === 'user')?.text;
      const title = conversationTitle(filename ? `Contract review — ${filename}` : 'Contract review', firstQuestion);
      set({ exporting: true });
      try {
        await downloadConversation(title, messages.map(contractMessageToExport), format);
      } finally {
        set({ exporting: false });
      }
    },

    clearConversation: () => {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      set({ messages: [], sending: false, analyzing: false, progressMessage: '' });
      // A fresh conversation gets its own History row.
      resetWorkspaceSessionKey('contracts');
    },

    restoreWorkspaceSession: async (payload) => {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      const prevUrl = get().contractFileUrl;
      if (prevUrl) URL.revokeObjectURL(prevUrl);
      const p = payload as {
        selectedDocumentId?: string | null;
        messages?: ContractChatMessage[];
        comparison?: {
          docs?: Array<{ id: string; label: string }>;
          comparisons?: ContractComparison[];
        } | null;
      };
      set({
        selectedDocumentId: p.selectedDocumentId || '',
        messages: Array.isArray(p.messages) ? p.messages : [],
        sending: false,
        analyzing: false,
        progressMessage: '',
        comparisonView: null,
        comparisonJump: null,
        contractText: null,
        contractFileUrl: null,
        contractTextDirty: false,
        viewerOpen: !!p.selectedDocumentId,
      });
      if (p.selectedDocumentId) void get().loadContractText();
      if (p.comparison?.comparisons?.length) {
        void get().openComparisonView(p.comparison.comparisons);
      } else if ((p.comparison?.docs?.length ?? 0) >= 2) {
        void get().openSplitDocs(p.comparison!.docs!.map((d) => ({ id: d.id, name: d.label })));
      }
    },

    // ── Split view: 2-4 documents side by side ───────────────────────
    comparisonView: null,
    comparisonJump: null,

    openSplitDocs: async (docs) => {
      const unique = docs.filter((d, i) => docs.findIndex((x) => x.id === d.id) === i).slice(0, 4);
      if (unique.length < 2) return;
      set({
        selectedDocumentId: unique[0].id,
        comparisonView: {
          docs: unique.map((d) => ({ id: d.id, label: d.name, text: '' })),
          comparisons: [],
          loading: true,
        },
        comparisonJump: null,
      });
      const texts = await Promise.all(unique.map((d) => loadDocText(d.id)));
      if (!get().comparisonView) return; // closed while loading
      set({
        comparisonView: {
          docs: unique.map((d, i) => ({ id: d.id, label: d.name, text: texts[i] })),
          comparisons: [],
          loading: false,
        },
      });
    },

    openComparisonView: async (comparisons) => {
      if (comparisons.length === 0) return;
      // Baseline (side A of every pair) first, then each compared document.
      const docs: Array<{ id: string; label: string }> = [];
      const first = comparisons[0];
      if (first.document_id_a) docs.push({ id: first.document_id_a, label: first.label_a });
      for (const c of comparisons) {
        if (c.document_id_b && !docs.some((d) => d.id === c.document_id_b)) {
          docs.push({ id: c.document_id_b, label: c.label_b });
        }
      }
      if (docs.length < 2) {
        toast('This comparison predates side-by-side view — run it again to open one.', 'info');
        return;
      }
      set({
        comparisonView: {
          docs: docs.map((d) => ({ ...d, text: '' })),
          comparisons,
          loading: true,
        },
        comparisonJump: null,
      });
      const texts = await Promise.all(docs.map((d) => loadDocText(d.id)));
      if (!get().comparisonView) return; // closed while loading
      if (texts.every((t) => !t)) {
        toast('Could not load the documents for side-by-side view.', 'error');
        set({ comparisonView: null });
        return;
      }
      set({
        comparisonView: {
          docs: docs.map((d, i) => ({ ...d, text: texts[i] })),
          comparisons,
          loading: false,
        },
      });
    },

    closeComparisonView: () => set({ comparisonView: null, comparisonJump: null }),

    // Compare every document open in the split view against the first one.
    compareOpenDocs: async (focus) => {
      const { comparisonView, sending, analyzing } = get();
      if (sending || analyzing) return;
      if (!comparisonView || comparisonView.docs.length < 2) {
        toast('Open two or more contracts first (multi-select in the file picker).', 'error');
        return;
      }
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      const names = comparisonView.docs.map((d) => d.label).join(', ');
      pushMessage({
        role: 'user',
        kind: 'text',
        text: focus?.trim() ? `Compare ${names} — ${focus.trim()}` : `Compare ${names}`,
      });
      set({
        analyzing: true,
        progressMessage: comparisonView.docs.length > 2
          ? 'Comparing every contract against the first, clause by clause…'
          : 'Comparing the two contracts clause by clause…',
      });
      try {
        const resp = await api.compareContracts(
          comparisonView.docs.map((d) => d.id),
          focus?.trim() || undefined,
        );
        pollContractJob(resp.job_id);
      } catch (e) {
        logger.error('contract compare failed', e);
        failChat(e instanceof Error ? e.message : 'Comparison failed.');
      }
    },

    // Jump to one clause in the split view (opens the right view first if needed).
    jumpToComparisonClause: async (comparison, clauseIndex) => {
      const view = get().comparisonView;
      let comparisonIndex = view ? view.comparisons.indexOf(comparison) : -1;
      if (comparisonIndex === -1) {
        // Open the message's full set so sibling comparisons stay visible.
        const { messages } = get();
        let comparisons: ContractComparison[] = [comparison];
        for (let i = messages.length - 1; i >= 0; i--) {
          const m = messages[i];
          if (m.kind === 'comparison_set' && m.comparisonSet?.comparisons.includes(comparison)) {
            comparisons = m.comparisonSet.comparisons;
            break;
          }
          if (m.kind === 'comparison' && m.comparison === comparison) break;
        }
        await get().openComparisonView(comparisons);
        comparisonIndex = Math.max(0, comparisons.indexOf(comparison));
      }
      set((st) => ({
        comparisonJump: { comparisonIndex, clauseIndex, seq: (st.comparisonJump?.seq || 0) + 1 },
      }));
    },
  };
});

registerReset(() => {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  const url = useContractsStore.getState().contractFileUrl;
  if (url) URL.revokeObjectURL(url);
  useContractsStore.setState(useContractsStore.getInitialState(), true);
});
