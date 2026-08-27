import { api } from './client';
import type { WorkspaceSessionDetail, WorkspaceSessionSummary } from './types';

Object.assign(api, {
  async listWorkspaceSessions(): Promise<{ sessions: WorkspaceSessionSummary[] }> {
    return api.request('/workspace-sessions');
  },

  async createWorkspaceSession(
    surface: string,
    title: string,
    payload: Record<string, unknown>,
  ): Promise<WorkspaceSessionSummary> {
    return api.request('/workspace-sessions', {
      method: 'POST',
      body: JSON.stringify({ surface, title, payload }),
    });
  },

  async updateWorkspaceSession(
    id: string,
    updates: { title?: string; payload?: Record<string, unknown> },
  ): Promise<WorkspaceSessionSummary> {
    return api.request(`/workspace-sessions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },

  async getWorkspaceSession(id: string): Promise<WorkspaceSessionDetail> {
    return api.request(`/workspace-sessions/${id}`);
  },

  async deleteWorkspaceSession(id: string): Promise<{ status: string; id: string }> {
    return api.request(`/workspace-sessions/${id}`, { method: 'DELETE' });
  },
});
