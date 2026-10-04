import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { DraftPlan } from '../api/types';

vi.mock('../api', () => ({
  api: {
    planDraft: vi.fn(),
    generateDraft: vi.fn(),
    getContractJob: vi.fn(),
    contractChat: vi.fn(),
    exportDraft: vi.fn(),
  },
}));
vi.mock('./workspaceSessionsStore', () => ({
  persistWorkspaceSession: vi.fn(),
  resetWorkspaceSessionKey: vi.fn(),
}));

import { api } from '../api';
import { useDraftingStore, WORDS_PER_PAGE } from './draftingStore';

const mocked = api as unknown as {
  planDraft: ReturnType<typeof vi.fn>;
  generateDraft: ReturnType<typeof vi.fn>;
  getContractJob: ReturnType<typeof vi.fn>;
  contractChat: ReturnType<typeof vi.fn>;
};

const PLAN: DraftPlan = {
  title: 'Master Services Agreement',
  document_type: 'MSA',
  sections: [
    { number: 1, title: 'Definitions', brief: 'Defined terms.', exclude: '', target_words: 400 },
    { number: 2, title: 'Services', brief: 'Scope.', exclude: 'Fees (Section 3).', target_words: 600 },
    { number: 3, title: 'Fees', brief: 'Fees and invoicing.', exclude: '', target_words: 500 },
  ],
  definitions: '"Supplier" means Acme Ltd.',
  style_guide: 'Numbered sections.',
  target_words: 1500,
  references_mode: 'full',
};

const flush = () => new Promise((r) => setTimeout(r, 0));
const lastText = () => { const m = useDraftingStore.getState().messages; return m[m.length - 1]?.text; };

describe('draftingStore', () => {
  beforeEach(() => {
    useDraftingStore.setState(useDraftingStore.getInitialState(), true);
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // ==================== Target length ====================

  it('setTargetPages rounds, clamps and clears', () => {
    const st = useDraftingStore.getState();
    st.setTargetPages(30.4);
    expect(useDraftingStore.getState().targetPages).toBe(30);
    st.setTargetPages(9999);
    expect(useDraftingStore.getState().targetPages).toBe(200);
    st.setTargetPages(0);
    expect(useDraftingStore.getState().targetPages).toBeNull();
    st.setTargetPages(null);
    expect(useDraftingStore.getState().targetPages).toBeNull();
  });

  // ==================== Plan editing ====================

  it('updatePlanSection patches one section and recomputes the word total', () => {
    useDraftingStore.setState({ draftPlan: PLAN });
    useDraftingStore.getState().updatePlanSection(1, { title: 'Scope of Services', target_words: 900 });
    const plan = useDraftingStore.getState().draftPlan!;
    expect(plan.sections[1].title).toBe('Scope of Services');
    expect(plan.sections[0].title).toBe('Definitions');
    expect(plan.target_words).toBe(400 + 900 + 500);
  });

  it('removePlanSection renumbers and never removes the last section', () => {
    useDraftingStore.setState({ draftPlan: PLAN });
    useDraftingStore.getState().removePlanSection(0);
    let plan = useDraftingStore.getState().draftPlan!;
    expect(plan.sections.map((s) => s.number)).toEqual([1, 2]);
    expect(plan.sections[0].title).toBe('Services');
    expect(plan.target_words).toBe(1100);

    useDraftingStore.getState().removePlanSection(0);
    useDraftingStore.getState().removePlanSection(0);
    plan = useDraftingStore.getState().draftPlan!;
    expect(plan.sections).toHaveLength(1);
  });

  it('addPlanSection inserts after the given index with contiguous numbering', () => {
    useDraftingStore.setState({ draftPlan: PLAN });
    useDraftingStore.getState().addPlanSection(0);
    const plan = useDraftingStore.getState().draftPlan!;
    expect(plan.sections.map((s) => s.number)).toEqual([1, 2, 3, 4]);
    expect(plan.sections[1].title).toBe('New section');
    expect(plan.sections[2].title).toBe('Services');
  });

  it('updatePlanField edits the shared material', () => {
    useDraftingStore.setState({ draftPlan: PLAN });
    useDraftingStore.getState().updatePlanField('definitions', '"Supplier" means Beta LLC.');
    expect(useDraftingStore.getState().draftPlan!.definitions).toBe('"Supplier" means Beta LLC.');
  });

  it('discardPlan clears the plan and says so', () => {
    useDraftingStore.setState({ draftPlan: PLAN, planRequest: { message: 'x', referenceIds: [], targetPages: 5 } });
    useDraftingStore.getState().discardPlan();
    const st = useDraftingStore.getState();
    expect(st.draftPlan).toBeNull();
    expect(st.planRequest).toBeNull();
    expect(lastText()).toMatch(/Plan discarded/);
  });

  // ==================== Plan-first flow ====================

  it('a fresh draft with a target length plans first and lands the plan for review', async () => {
    mocked.planDraft.mockResolvedValue({ type: 'draft_plan_started', job_id: 'job-1' });
    mocked.getContractJob.mockResolvedValue({
      job_id: 'job-1',
      status: 'completed',
      result: { kind: 'draft_plan', plan: PLAN, target_pages: 30 },
    });
    useDraftingStore.setState({
      targetPages: 30,
      draftReferences: [{ id: 'doc-1', name: 'Old MSA.pdf' }],
    });

    await useDraftingStore.getState().sendDraftMessage('Draft an MSA', 'draft');
    await flush();

    expect(mocked.planDraft).toHaveBeenCalledWith('Draft an MSA', ['doc-1'], 30);
    expect(mocked.contractChat).not.toHaveBeenCalled();
    const st = useDraftingStore.getState();
    expect(st.sending).toBe(false);
    expect(st.draftPlan).toEqual(PLAN);
    expect(st.planRequest).toEqual({ message: 'Draft an MSA', referenceIds: ['doc-1'], targetPages: 30 });
    expect(st.draftWorkspace).toBeNull();
    const pages = Math.round(1500 / WORDS_PER_PAGE);
    expect(lastText()).toContain(`3 sections, about ${pages} pages`);
    expect(lastText()).toContain('full reference documents');
  });

  it('without a target length the single-pass chat path is used', async () => {
    mocked.contractChat.mockResolvedValue({ type: 'draft_started', job_id: 'job-2' });
    mocked.getContractJob.mockResolvedValue({
      job_id: 'job-2',
      status: 'completed',
      result: { kind: 'draft', title: 'Demand Letter', text: 'Dear Sir…' },
    });

    await useDraftingStore.getState().sendDraftMessage('Draft a demand letter', 'draft');
    await flush();

    expect(mocked.planDraft).not.toHaveBeenCalled();
    expect(mocked.contractChat).toHaveBeenCalled();
    expect(useDraftingStore.getState().draftWorkspace).toEqual({ title: 'Demand Letter', text: 'Dear Sir…', dirty: false });
  });

  it('generateFromPlan sends the edited plan back and lands the draft', async () => {
    mocked.generateDraft.mockResolvedValue({ type: 'draft_started', job_id: 'job-3' });
    mocked.getContractJob.mockResolvedValue({
      job_id: 'job-3',
      status: 'completed',
      result: {
        kind: 'draft',
        title: 'Master Services Agreement',
        text: 'MASTER SERVICES AGREEMENT\n\n1. DEFINITIONS…',
        sections: [{ number: 1, title: 'Definitions', text: '1. DEFINITIONS…' }],
        reconcile_notes: ['Fixed a cross-reference in Section 2.'],
        references_mode: 'full',
      },
    });
    useDraftingStore.setState({
      draftPlan: PLAN,
      planRequest: { message: 'Draft an MSA', referenceIds: ['doc-1'], targetPages: 30 },
    });

    await useDraftingStore.getState().generateFromPlan();
    await flush();

    expect(mocked.generateDraft).toHaveBeenCalledWith(PLAN, 'Draft an MSA', ['doc-1']);
    const st = useDraftingStore.getState();
    expect(st.draftWorkspace?.title).toBe('Master Services Agreement');
    expect(st.draftPlan).toBeNull();
    expect(st.planRequest).toBeNull();
    expect(lastText()).toContain('1 sections drafted in parallel');
    expect(lastText()).toContain('Fixed a cross-reference in Section 2.');
  });

  it('generateFromPlan refuses a section without a title', async () => {
    useDraftingStore.setState({
      draftPlan: { ...PLAN, sections: [{ ...PLAN.sections[0], title: '  ' }] },
      planRequest: { message: 'x', referenceIds: [], targetPages: 5 },
    });
    await useDraftingStore.getState().generateFromPlan();
    expect(mocked.generateDraft).not.toHaveBeenCalled();
    expect(useDraftingStore.getState().sending).toBe(false);
  });

  // ==================== Polling & revision ====================

  it('surfaces job progress while polling, then settles', async () => {
    vi.useFakeTimers();
    mocked.contractChat.mockResolvedValue({ type: 'draft_started', job_id: 'job-4' });
    mocked.getContractJob
      .mockResolvedValueOnce({ job_id: 'job-4', status: 'processing', progress: { message: 'Drafted section 2 of 3: Services', fraction: 0.5 } })
      .mockResolvedValueOnce({ job_id: 'job-4', status: 'completed', result: { kind: 'draft', title: 'T', text: 'body' } });

    const send = useDraftingStore.getState().sendDraftMessage('Draft it', 'draft');
    await vi.advanceTimersByTimeAsync(0);
    await send;
    expect(useDraftingStore.getState().progressMessage).toBe('Drafted section 2 of 3: Services');

    await vi.advanceTimersByTimeAsync(2000);
    const st = useDraftingStore.getState();
    expect(st.sending).toBe(false);
    expect(st.draftWorkspace?.text).toBe('body');
  });

  it('a scoped revision keeps the workspace title and names the sections changed', async () => {
    mocked.contractChat.mockResolvedValue({ type: 'draft_started', job_id: 'job-5' });
    mocked.getContractJob.mockResolvedValue({
      job_id: 'job-5',
      status: 'completed',
      result: { kind: 'draft', title: '', text: 'revised body', revised_sections: [3, 5] },
    });
    useDraftingStore.setState({ draftWorkspace: { title: 'Original Title', text: 'body', dirty: false } });

    await useDraftingStore.getState().sendDraftMessage('Add a cure period', 'draft');
    await flush();

    const st = useDraftingStore.getState();
    expect(st.draftWorkspace).toEqual({ title: 'Original Title', text: 'revised body', dirty: false });
    expect(lastText()).toContain('sections 3, 5 updated');
    // The current draft is what gets revised — sent along with the instruction.
    expect(mocked.contractChat.mock.calls[0][3]).toBe('body');
  });

  it('a failed job reports the error and stops', async () => {
    mocked.contractChat.mockResolvedValue({ type: 'draft_started', job_id: 'job-6' });
    mocked.getContractJob.mockResolvedValue({ job_id: 'job-6', status: 'failed', error: 'Section 3 failed: down' });

    await useDraftingStore.getState().sendDraftMessage('Draft it', 'draft');
    await flush();

    const st = useDraftingStore.getState();
    expect(st.sending).toBe(false);
    expect(lastText()).toBe('Section 3 failed: down');
  });

  // ==================== Session restore ====================

  it('restoreWorkspaceSession brings back the plan, request and target length', async () => {
    await useDraftingStore.getState().restoreWorkspaceSession({
      messages: [{ id: 'm1', role: 'user', text: 'hi' }],
      draftPlan: PLAN,
      planRequest: { message: 'Draft an MSA', referenceIds: [], targetPages: 30 },
      targetPages: 30,
    });
    const st = useDraftingStore.getState();
    expect(st.draftPlan).toEqual(PLAN);
    expect(st.planRequest?.targetPages).toBe(30);
    expect(st.targetPages).toBe(30);
    expect(st.messages).toHaveLength(1);
  });

  it('restoreWorkspaceSession ignores a malformed plan', async () => {
    await useDraftingStore.getState().restoreWorkspaceSession({ draftPlan: { title: 'x' } });
    expect(useDraftingStore.getState().draftPlan).toBeNull();
  });
});
