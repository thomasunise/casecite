import { api } from './client';
import type { ChatSessionDetail, ChatSessionListResponse } from './types';

Object.assign(api, {
  async listChatSessions(): Promise<ChatSessionListResponse> {
    return api.request('/chat/sessions');
  },

  async getChatSession(sessionId: string): Promise<ChatSessionDetail> {
    return api.request(`/chat/sessions/${encodeURIComponent(sessionId)}`);
  },

  async deleteChatSession(sessionId: string): Promise<{ status: string; id: string }> {
    return api.request(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },
});
