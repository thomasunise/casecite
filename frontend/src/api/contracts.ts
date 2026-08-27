import { api, API_BASE_URL } from './client';
import type {
  ContractAnalysisJob,
  ContractAnalysisListItem,
  ContractAnalysisResult,
  ContractAnalyzePayload,
  ContractChatResponse,
  ContractCompareStarted,
  ContractJobStarted,
  DraftPlan,
} from './types';

Object.assign(api, {
  async analyzeContract(payload: ContractAnalyzePayload): Promise<{ job_id: string; poll_url?: string }> {
    return api.request('/contract-analysis/analyze?async=true', {
      method: 'POST',
      body: JSON.stringify({
        document_id: payload.documentId ?? null,
        document_text: payload.documentText ?? null,
        contract_type: payload.contractType ?? 'auto',
        representing: payload.representing ?? null,
        posture: payload.posture ?? 'balanced',
      }),
    });
  },

  async getContractJob(jobId: string): Promise<ContractAnalysisJob> {
    return api.request(`/jobs/${jobId}`);
  },

  async listContractAnalyses(): Promise<{ analyses: ContractAnalysisListItem[] }> {
    return api.request('/contract-analysis/analyses');
  },

  async getContractAnalysis(id: string): Promise<ContractAnalysisResult> {
    return api.request(`/contract-analysis/analyses/${encodeURIComponent(id)}`);
  },

  async contractChat(documentId: string | null, message: string, mode?: string, draftText?: string, referenceIds?: string[]): Promise<ContractChatResponse> {
    // 200 → {type:"answer", ...}; 202 → {type:"analysis_started", ...}.
    // api.request parses JSON for any 2xx status, so both shapes come back
    // as-is and are discriminated on `type`. Answers can take a while to
    // generate, so allow more than the default 30s.
    return api.request('/contract-analysis/chat', {
      method: 'POST',
      body: JSON.stringify({
        document_id: documentId || null,
        message,
        mode: mode || null,
        draft_text: draftText || null,
        reference_document_ids: referenceIds?.length ? referenceIds : null,
      }),
      timeout: 120000,
    });
  },

  async exportContractAnalysis(id: string, format: 'docx' | 'md'): Promise<Blob> {
    const resp = await api.authFetch(
      `${API_BASE_URL}/contract-analysis/analyses/${encodeURIComponent(id)}/export?format=${format}`
    );
    if (!resp.ok) {
      throw new Error(`Export failed (${resp.status})`);
    }
    return resp.blob();
  },

  async generatePracticeProfile(practiceArea: string): Promise<{ practice_area: string; profile: string }> {
    return api.request('/contract-analysis/practice-profile', {
      method: 'POST',
      body: JSON.stringify({ practice_area: practiceArea }),
      timeout: 120000,
    });
  },

  async compareContracts(documentIds: string[], focus?: string): Promise<ContractCompareStarted> {
    // Always 202 — comparisons run as a background job. 2-4 documents; the
    // first is the baseline every other document is compared against.
    return api.request('/contract-analysis/compare', {
      method: 'POST',
      body: JSON.stringify({ document_ids: documentIds, focus: focus || null }),
    });
  },

  async exportRedlines(
    analysisId: string,
    excludeRefs: string[],
    overrides: Record<string, string> = {},
  ): Promise<Blob> {
    // `exclude` carries the refs the user REJECTED; `overrides` carries the
    // user's own edits to proposed wording (ref -> replacement text).
    const resp = await api.authFetch(
      `${API_BASE_URL}/contract-analysis/analyses/${encodeURIComponent(analysisId)}/redline-export`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exclude: excludeRefs, overrides }),
      },
    );
    if (!resp.ok) {
      throw new Error(`Redline export failed (${resp.status})`);
    }
    return resp.blob();
  },

  async planDraft(message: string, referenceIds: string[], targetPages: number): Promise<ContractJobStarted> {
    // Long drafts, phase 1: always 202 — the plan is built as a job from the
    // full reference bundle and comes back for review before anything is written.
    return api.request('/contract-analysis/draft/plan', {
      method: 'POST',
      body: JSON.stringify({
        message,
        reference_document_ids: referenceIds.length ? referenceIds : null,
        target_pages: targetPages,
      }),
      timeout: 120000,
    });
  },

  async generateDraft(plan: DraftPlan, message: string, referenceIds: string[]): Promise<ContractJobStarted> {
    // Long drafts, phases 2-3: the (edited) plan goes back; every section is
    // drafted in parallel, then reconciled. Always 202.
    return api.request('/contract-analysis/draft/generate', {
      method: 'POST',
      body: JSON.stringify({
        plan,
        message,
        reference_document_ids: referenceIds.length ? referenceIds : null,
      }),
      timeout: 120000,
    });
  },

  async exportDraft(title: string, text: string): Promise<Blob> {
    const resp = await api.authFetch(`${API_BASE_URL}/contract-analysis/draft-export`, {
      method: 'POST',
      body: JSON.stringify({ title, text }),
    });
    if (!resp.ok) {
      throw new Error(`Draft export failed (${resp.status})`);
    }
    return resp.blob();
  },
});
