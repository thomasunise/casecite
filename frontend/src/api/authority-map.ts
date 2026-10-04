import { api } from './client';
import type { AuthorityMapJob, AuthorityMapPayload } from './types';

Object.assign(api, {
  async submitAuthorityMap(payload: AuthorityMapPayload): Promise<{ job_id: string }> {
    return api.request('/authority-map/analyze', {
      method: 'POST',
      body: JSON.stringify({
        document_text: payload.documentText,
        document_name: payload.documentName ?? null,
        jurisdiction: payload.jurisdiction ?? null,
      }),
    });
  },

  async getAuthorityMapJob(jobId: string): Promise<AuthorityMapJob> {
    return api.request(`/jobs/${jobId}`);
  },

  async deleteAuthorityMap(runId: string): Promise<{ status: string; id: string }> {
    return api.request(`/authority-map/${encodeURIComponent(runId)}`, { method: 'DELETE' });
  },

  async getCaseOpinion(opinionId: string): Promise<{ case_name?: string; opinion_text?: string; syllabus?: string; [k: string]: unknown }> {
    return api.request(`/tools/cases/${opinionId}`);
  },
});
