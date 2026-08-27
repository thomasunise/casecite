import { create } from 'zustand';
import { api } from '../api';
import type {
  ContractDraft, ContractJobResult, DraftPlan, DraftPlanSection,
} from '../api/types';
import { useUIStore } from './uiStore';
import { persistWorkspaceSession, resetWorkspaceSessionKey } from './workspaceSessionsStore';
import { registerReset } from './resetRegistry';
import { downloadBlob } from '../utils/downloadBlob';
import logger from '../utils/logger';
import { conversationTitle, downloadConversation } from '../utils/conversationExport';
import type { ConversationExportFormat } from '../api/types';

export interface DraftingMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
}

/** What the plan was requested for — sent back unchanged at generate time. */
export interface DraftPlanRequest {
  message: string;
  referenceIds: string[];
  targetPages: number;
}

/** Dense legal prose: ~450 words per page. Mirrors the backend constant. */
export const WORDS_PER_PAGE = 450;

export interface DraftingState {
  messages: DraftingMessage[];
  sending: boolean;
  progressMessage: string;
  exporting: boolean;
  /** The draft IS the page; the composer revises it. */
  draftWorkspace: { title: string; text: string; dirty: boolean } | null;
  /** Source documents the draft is built from ("based on this service agreement"). */
  draftReferences: Array<{ id: string; name: string }>;
  /**
   * Target length for a fresh draft. null = one-pass drafting (letters,
   * amendments). A number switches to the long-document pipeline: plan →
   * review → every section drafted in its own context window → reconcile.
   */
  targetPages: number | null;
  setTargetPages: (pages: number | null) => void;
  /** A long-draft plan awaiting review. Nothing is written until it's approved. */
  draftPlan: DraftPlan | null;
  planRequest: DraftPlanRequest | null;
  updatePlanField: (field: 'title' | 'document_type' | 'definitions' | 'style_guide', value: string) => void;
  updatePlanSection: (index: number, patch: Partial<DraftPlanSection>) => void;
  removePlanSection: (index: number) => void;
  addPlanSection: (afterIndex: number) => void;
  discardPlan: () => void;
  /** Approve the plan: draft every section, then reconcile. */
  generateFromPlan: () => Promise<void>;
  updateDraftText: (text: string) => void;
  closeDraftWorkspace: () => void;
  /** Attach already-indexed knowledge-base documents as drafting sources. */
  attachDraftReferences: (docs: Array<{ id: string; name: string }>) => void;
  removeDraftReference: (id: string) => void;
  /** Draft or revise (mode 'draft'), or ask about the draft (mode undefined). */
  sendDraftMessage: (text: string, mode?: 'draft') => Promise<void>;
  /** A draft produced elsewhere (e.g. Contracts routed a draft ask) lands here. */
  receiveDraft: (draft: ContractDraft) => void;
  exportDraftDocx: () => Promise<void>;
  clearConversation: () => void;
  exportConversation: (format: ConversationExportFormat) => Promise<void>;
  restoreWorkspaceSession: (payload: Record<string, unknown>) => Promise<void>;
}

let messageSeq = 0;
const nextId = () => `dmsg-${Date.now()}-${++messageSeq}`;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function toast(msg: string, type = 'info') {
  try { useUIStore.getState().addToast(msg, type); } catch { /* noop */ }
}

/** Keep section numbers contiguous after an insert or delete. */
function renumber(sections: DraftPlanSection[]): DraftPlanSection[] {
  return sections.map((s, i) => ({ ...s, number: i + 1 }));
}

function planWords(plan: DraftPlan): number {
  return plan.sections.reduce((sum, s) => sum + (Number(s.target_words) || 0), 0);
}

export const useDraftingStore = create<DraftingState>((set, get) => {
  const persistSession = () => {
    const st = get();
    if (st.messages.length === 0 && !st.draftWorkspace && !st.draftPlan) return;
    const title = st.draftWorkspace?.title
      || st.draftPlan?.title
      || st.messages.find((m) => m.role === 'user')?.text.slice(0, 80)
      || 'Draft';
    persistWorkspaceSession('drafting', 'drafting', title, {
      messages: st.messages,
      draftWorkspace: st.draftWorkspace,
      draftReferences: st.draftReferences,
      targetPages: st.targetPages,
      draftPlan: st.draftPlan,
      planRequest: st.planRequest,
    });
  };

  const pushMessage = (role: 'user' | 'assistant', text: string) => {
    set((st) => ({ messages: [...st.messages, { id: nextId(), role, text }] }));
    if (role === 'assistant') queueMicrotask(persistSession);
  };

  const fail = (msg: string) => {
    set({ sending: false, progressMessage: '' });
    pushMessage('assistant', msg);
    toast(msg, 'error');
  };

  const settle = (result: ContractJobResult) => {
    if ('kind' in result && result.kind === 'draft_plan') {
      const plan = result.plan;
      const pages = Math.round(planWords(plan) / WORDS_PER_PAGE);
      set({ draftPlan: plan, draftWorkspace: null });
      const refs = plan.references_mode === 'excerpts'
        ? ' The references are too large to send whole, so each section will read the excerpts most relevant to it plus the shared definitions.'
        : plan.references_mode === 'full'
          ? ' Every section will read the full reference documents.'
          : '';
      pushMessage(
        'assistant',
        `Plan ready: ${plan.sections.length} sections, about ${pages} pages.${refs} Review it on the page — edit any section's brief, add or remove sections — then generate.`,
      );
      queueMicrotask(persistSession);
      return;
    }
    if ('kind' in result && result.kind === 'draft') {
      const existing = get().draftWorkspace;
      const isRevision = !!existing;
      const title = result.title || existing?.title || 'Draft';
      set({
        draftWorkspace: { title, text: result.text, dirty: false },
        draftPlan: null,
        planRequest: null,
      });
      if (isRevision) {
        const revised = Array.isArray(result.revised_sections) ? result.revised_sections : [];
        pushMessage(
          'assistant',
          revised.length > 0
            ? `Draft revised — section${revised.length > 1 ? 's' : ''} ${revised.join(', ')} updated; everything else untouched.`
            : 'Draft revised — the document is updated.',
        );
        return;
      }
      const notes = result.reconcile_notes?.filter((n) => n && n !== 'No changes.') ?? [];
      const sectionCount = result.sections?.length ?? 0;
      const summary = sectionCount
        ? `"${title}" is ready — ${sectionCount} sections drafted in parallel and reconciled.`
        : `"${title}" is ready.`;
      const noteText = notes.length
        ? `\n\nReconcile pass:\n${notes.map((n) => `- ${n}`).join('\n')}`
        : '';
      pushMessage(
        'assistant',
        `${summary} Keep steering it from the composer, or select any text in the document to rewrite it.${noteText}`,
      );
      return;
    }
    fail('The job finished with an unexpected result.');
  };

  const pollJob = (jobId: string) => {
    const poll = async (attempt: number) => {
      try {
        const job = await api.getContractJob(jobId);
        if (job.status === 'completed') {
          set({ sending: false, progressMessage: '' });
          if (job.result) settle(job.result);
          else fail('The job finished but returned no result.');
          return;
        }
        if (job.status === 'failed' || job.status === 'cancelled') {
          fail(job.error || 'Drafting failed.');
          return;
        }
        if (job.progress?.message) set({ progressMessage: job.progress.message });
        // Long drafts run many calls; allow up to 20 minutes.
        if (attempt > 600) { fail('Timed out waiting for the draft.'); return; }
        pollTimer = setTimeout(() => poll(attempt + 1), 2000);
      } catch (e) {
        fail(e instanceof Error ? e.message : 'Polling failed.');
      }
    };
    poll(0);
  };

  return {
    messages: [],
    sending: false,
    progressMessage: '',
    exporting: false,
    draftWorkspace: null,
    draftReferences: [],
    targetPages: null,
    draftPlan: null,
    planRequest: null,

    setTargetPages: (pages) => {
      const clean = pages && pages > 0 ? Math.min(200, Math.round(pages)) : null;
      set({ targetPages: clean });
    },

    updatePlanField: (field, value) => {
      set((st) => st.draftPlan ? { draftPlan: { ...st.draftPlan, [field]: value } } : {});
      queueMicrotask(persistSession);
    },

    updatePlanSection: (index, patch) => {
      set((st) => {
        if (!st.draftPlan) return {};
        const sections = st.draftPlan.sections.map((s, i) => (i === index ? { ...s, ...patch } : s));
        return { draftPlan: { ...st.draftPlan, sections, target_words: planWords({ ...st.draftPlan, sections }) } };
      });
      queueMicrotask(persistSession);
    },

    removePlanSection: (index) => {
      set((st) => {
        if (!st.draftPlan || st.draftPlan.sections.length <= 1) return {};
        const sections = renumber(st.draftPlan.sections.filter((_, i) => i !== index));
        return { draftPlan: { ...st.draftPlan, sections, target_words: planWords({ ...st.draftPlan, sections }) } };
      });
      queueMicrotask(persistSession);
    },

    addPlanSection: (afterIndex) => {
      set((st) => {
        if (!st.draftPlan) return {};
        const blank: DraftPlanSection = { number: 0, title: 'New section', brief: '', exclude: '', target_words: 400 };
        const sections = [...st.draftPlan.sections];
        sections.splice(afterIndex + 1, 0, blank);
        const renumbered = renumber(sections);
        return { draftPlan: { ...st.draftPlan, sections: renumbered, target_words: planWords({ ...st.draftPlan, sections: renumbered }) } };
      });
      queueMicrotask(persistSession);
    },

    discardPlan: () => {
      set({ draftPlan: null, planRequest: null });
      pushMessage('assistant', 'Plan discarded. Describe the draft again, or change the target length, to plan afresh.');
    },

    generateFromPlan: async () => {
      const { draftPlan, planRequest, sending } = get();
      if (!draftPlan || !planRequest || sending) return;
      const empty = draftPlan.sections.find((s) => !s.title.trim());
      if (empty) { toast('Every section needs a title.', 'error'); return; }
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      const n = draftPlan.sections.length;
      pushMessage('user', `Generate the draft from the plan (${n} sections).`);
      set({ sending: true, progressMessage: `Drafting ${n} sections in parallel…` });
      try {
        const resp = await api.generateDraft(draftPlan, planRequest.message, planRequest.referenceIds);
        pollJob(resp.job_id);
      } catch (e) {
        logger.error('draft generation failed', e);
        fail(e instanceof Error ? e.message : 'Failed to start drafting.');
      }
    },

    updateDraftText: (text) => {
      set((st) => st.draftWorkspace
        ? { draftWorkspace: { ...st.draftWorkspace, text, dirty: true } }
        : {});
      queueMicrotask(persistSession);
    },

    closeDraftWorkspace: () => set({ draftWorkspace: null }),

    attachDraftReferences: (docs) => {
      set((st) => {
        const merged = [...st.draftReferences];
        for (const doc of docs) {
          if (merged.some((r) => r.id === doc.id)) continue;
          if (merged.length >= 4) {
            toast('Up to 4 reference documents per draft.', 'error');
            break;
          }
          merged.push({ id: doc.id, name: doc.name });
        }
        return { draftReferences: merged };
      });
      queueMicrotask(persistSession);
    },

    removeDraftReference: (id) =>
      set((st) => ({ draftReferences: st.draftReferences.filter((r) => r.id !== id) })),

    sendDraftMessage: async (text, mode = 'draft') => {
      const trimmed = text.trim();
      const { sending, draftWorkspace, draftReferences, targetPages } = get();
      if (!trimmed || sending) return;
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      pushMessage('user', trimmed);
      const referenceIds = mode === 'draft' ? draftReferences.map((r) => r.id) : [];

      // A fresh draft with a target length goes through the long-document
      // pipeline: plan first, generate only once the plan is approved.
      if (mode === 'draft' && !draftWorkspace && targetPages) {
        set({
          sending: true,
          progressMessage: 'Reading the reference documents and planning the sections…',
          draftPlan: null,
          planRequest: { message: trimmed, referenceIds, targetPages },
        });
        try {
          const resp = await api.planDraft(trimmed, referenceIds, targetPages);
          pollJob(resp.job_id);
        } catch (e) {
          logger.error('draft planning failed', e);
          fail(e instanceof Error ? e.message : 'Failed to plan the draft.');
        }
        return;
      }

      set({
        sending: true,
        progressMessage: draftWorkspace ? 'Revising the draft…' : 'Drafting…',
      });
      try {
        const resp = await api.contractChat(
          null,
          trimmed,
          mode,
          draftWorkspace?.text || undefined,
          referenceIds.length > 0 ? referenceIds : undefined,
        );
        if (resp.type === 'draft_started') {
          pollJob(resp.job_id);
        } else if (resp.type === 'answer') {
          set({ sending: false, progressMessage: '' });
          pushMessage('assistant', resp.answer || '');
        } else if (resp.type === 'clarify') {
          set({ sending: false, progressMessage: '' });
          pushMessage('assistant', resp.question || 'Tell me more about what you need.');
        } else {
          set({ sending: false, progressMessage: '' });
          pushMessage('assistant', 'Done.');
        }
      } catch (e) {
        logger.error('drafting send failed', e);
        fail(e instanceof Error ? e.message : 'Failed to send.');
      }
    },

    receiveDraft: (draft) => {
      settle({ ...draft, kind: 'draft' });
    },

    exportDraftDocx: async () => {
      const { draftWorkspace, exporting } = get();
      if (!draftWorkspace || exporting) return;
      set({ exporting: true });
      try {
        const blob = await api.exportDraft(draftWorkspace.title || 'Draft', draftWorkspace.text);
        downloadBlob(blob, `${(draftWorkspace.title || 'draft').replace(/[^\w-]+/g, '-')}.docx`);
        toast('Draft downloaded.', 'success');
      } catch (e) {
        logger.error('draft export failed', e);
        toast(e instanceof Error ? e.message : 'Export failed.', 'error');
      } finally {
        set({ exporting: false });
      }
    },

    exportConversation: async (format) => {
      const { messages, exporting, draftWorkspace } = get();
      if (exporting) return;
      const firstQuestion = messages.find((m) => m.role === 'user')?.text;
      const title = conversationTitle(draftWorkspace?.title ? `Drafting — ${draftWorkspace.title}` : 'Drafting', firstQuestion);
      set({ exporting: true });
      try {
        await downloadConversation(
          title,
          messages.map((m) => ({ role: m.role, text: m.text })),
          format,
        );
      } finally {
        set({ exporting: false });
      }
    },

    clearConversation: () => {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      set({ messages: [], sending: false, progressMessage: '', draftPlan: null, planRequest: null });
      resetWorkspaceSessionKey('drafting');
    },

    restoreWorkspaceSession: async (payload) => {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      const p = payload as {
        messages?: DraftingMessage[];
        draftWorkspace?: { title: string; text: string; dirty: boolean } | null;
        draftReferences?: Array<{ id: string; name: string }>;
        targetPages?: number | null;
        draftPlan?: DraftPlan | null;
        planRequest?: DraftPlanRequest | null;
      };
      set({
        messages: Array.isArray(p.messages) ? p.messages : [],
        sending: false,
        progressMessage: '',
        draftWorkspace: p.draftWorkspace ?? null,
        draftReferences: Array.isArray(p.draftReferences) ? p.draftReferences : [],
        targetPages: typeof p.targetPages === 'number' ? p.targetPages : null,
        draftPlan: p.draftPlan && Array.isArray(p.draftPlan.sections) ? p.draftPlan : null,
        planRequest: p.planRequest ?? null,
      });
    },
  };
});

registerReset(() => {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
  useDraftingStore.setState(useDraftingStore.getInitialState(), true);
});
