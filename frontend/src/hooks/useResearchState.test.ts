import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { RagSettings } from '../types';

vi.mock('../api', () => ({
  api: {
    query: vi.fn(),
    listChatSessions: vi.fn(),
    getChatSession: vi.fn(),
    deleteChatSession: vi.fn(),
  },
}));

vi.mock('../utils', () => ({
  generateId: vi.fn(() => 'test-id-' + Math.random().toString(36).slice(2, 8)),
  parseUtcDate: (timestamp: string) => new Date(timestamp + 'Z'),
}));

import { useResearchState } from './useResearchState';
import { api } from '../api';

const mockRagSettings: RagSettings = {
  vectorDb: 'chroma',
  indexName: 'test-index',
  embeddingModel: 'text-embedding-3-small',
  dimensions: 1536,
  chunkSize: 512,
  chunkOverlap: 50,
  similarityThreshold: 0.55,
  topK: 10,
  enableReranking: false,
  hybridSearch: false,
  citationVerification: true,
  contextCompression: false,
  queryExpansion: false,
  sourceTracking: true,
  llmModel: 'gpt-5.5',
  temperature: 0.1,
  maxTokens: 4096,
  batchSize: 10,
};

describe('useResearchState', () => {
  const defaultProps = {
    addToast: vi.fn(),
    ragSettings: mockRagSettings,
    activeMode: 'research',
    setActiveMode: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('starts with empty state', () => {
    const { result } = renderHook(() => useResearchState(defaultProps));
    expect(result.current.messages).toEqual([]);
    expect(result.current.inputValue).toBe('');
    expect(result.current.isProcessing).toBe(false);
    expect(result.current.processingStage).toBe('');
    expect(result.current.selectedCitation).toBeNull();
    expect(result.current.allCitations).toEqual([]);
    expect(result.current.citationFilter).toBe('all');
    expect(result.current.currentSessionId).toBeNull();
    expect(result.current.chatSessions).toEqual([]);
    // Intent and case-law routing are server-side now; scope is the only control.
    expect(result.current.mainDocFilter).toBeNull();
  });

  it('starts with initial sessionStats', () => {
    const { result } = renderHook(() => useResearchState(defaultProps));
    expect(result.current.sessionStats).toEqual({
      queries: 0,
      citations: 0,
      approved: 0,
      rejected: 0,
      pending: 0,
    });
  });

  it('does NOT hydrate citations from localStorage — sources are per-search', () => {
    // Persisted citations resurrected phantom sources from dead sessions.
    localStorage.setItem(
      'wl_citations',
      JSON.stringify([{ id: 'c1', text: 'Stale citation', status: 'pending' }])
    );
    const { result } = renderHook(() => useResearchState(defaultProps));
    expect(result.current.allCitations).toEqual([]);
  });

  describe('handleSend', () => {
    it('does nothing with empty input', async () => {
      const { result } = renderHook(() => useResearchState(defaultProps));
      await act(async () => {
        await result.current.handleSend();
      });
      expect(api.query).not.toHaveBeenCalled();
    });

    it('sends query and adds messages on success', async () => {
      (api.query as any).mockResolvedValue({
        response: 'Here is the answer',
        citations: [
          {
            text: 'Source text',
            source: 'doc.pdf',
            relevance_score: 0.9,
            chunk_index: 0,
          },
        ],
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('What is contract law?'));
      await act(async () => {
        await result.current.handleSend();
      });

      expect(api.query).toHaveBeenCalledWith(
        'What is contract law?',
        'research',
        expect.objectContaining({ topK: 10, sessionId: null })
      );
      expect(result.current.messages.length).toBeGreaterThanOrEqual(2); // user + assistant
      expect(result.current.inputValue).toBe('');
      expect(result.current.isProcessing).toBe(false);
      expect(result.current.sessionStats.queries).toBe(1);
    });

    it('adopts the server session id and sends it on the next query', async () => {
      (api.query as any).mockResolvedValue({
        content: 'Answer',
        citations: [],
        session_id: 'sess-123',
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('first question'));
      await act(async () => {
        await result.current.handleSend();
      });

      expect(result.current.currentSessionId).toBe('sess-123');

      act(() => result.current.setInputValue('follow-up question'));
      await act(async () => {
        await result.current.handleSend();
      });

      expect(api.query).toHaveBeenLastCalledWith(
        'follow-up question',
        'research',
        expect.objectContaining({ sessionId: 'sess-123' })
      );
    });

    it('handles API error gracefully', async () => {
      (api.query as any).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('test'));
      await act(async () => {
        await result.current.handleSend();
      });

      // Should add an error message
      const lastMsg = result.current.messages[result.current.messages.length - 1];
      expect(lastMsg.type).toBe('assistant');
      expect(lastMsg.content).toMatch(/error|failed|sorry/i);
      expect(result.current.isProcessing).toBe(false);
    });
  });

  describe('loadSession', () => {
    const sessionDetail = {
      id: 'sess-42',
      title: 'Sublease questions',
      created_at: '2026-07-01T10:00:00',
      updated_at: '2026-07-01T10:05:00',
      messages: [
        {
          id: 'm1',
          role: 'user',
          content: 'Can we sublet the office?',
          citations: [],
          strategy: null,
          stats: null,
          created_at: '2026-07-01T10:00:00',
        },
        {
          id: 'm2',
          role: 'assistant',
          content: 'Yes, with landlord consent.',
          citations: [
            { id: 'c-old', source: 'lease.pdf', passage: 'Tenant may sublet...', confidence: 90 },
          ],
          strategy: null,
          stats: { docs_searched: 5, chunks_retrieved: 3, processing_time: '1.2s' },
          created_at: '2026-07-01T10:01:00',
        },
        {
          id: 'm3',
          role: 'user',
          content: 'What notice period applies?',
          citations: [],
          strategy: null,
          stats: null,
          created_at: '2026-07-01T10:04:00',
        },
        {
          id: 'm4',
          role: 'assistant',
          content: '30 days written notice.',
          citations: [
            { id: 'c-new', source: 'lease.pdf', passage: '30 days notice...', confidence: 85 },
          ],
          strategy: null,
          stats: { docs_searched: 5, chunks_retrieved: 2, processing_time: '0.9s' },
          created_at: '2026-07-01T10:05:00',
        },
      ],
    };

    it('maps the persisted thread into chat messages', async () => {
      (api.getChatSession as any).mockResolvedValue(sessionDetail);

      const { result } = renderHook(() => useResearchState(defaultProps));
      await act(async () => {
        await result.current.loadSession('sess-42');
      });

      expect(api.getChatSession).toHaveBeenCalledWith('sess-42');
      expect(result.current.messages).toHaveLength(4);
      expect(result.current.messages[0].type).toBe('user');
      expect(result.current.messages[0].content).toBe('Can we sublet the office?');
      expect(result.current.messages[1].type).toBe('assistant');
      expect(result.current.messages[1].citations?.[0].id).toBe('c-old');
      expect(result.current.messages[1].stats?.docsSearched).toBe(5);
      expect(result.current.messages[1].stats?.processingTime).toBe('1.2s');
      expect(result.current.messages[3].timestamp).toBeInstanceOf(Date);

      // Sources panel accumulates EVERY exchange's citations, each tagged with
      // its message and question for per-question grouping + jump-to-answer.
      expect(result.current.allCitations).toHaveLength(2);
      expect(result.current.allCitations[0].id).toBe('c-old');
      expect(result.current.allCitations[0].messageId).toBe('m2');
      expect(result.current.allCitations[0].sourceQuery).toBe('Can we sublet the office?');
      expect(result.current.allCitations[1].id).toBe('c-new');
      expect(result.current.allCitations[1].messageId).toBe('m4');

      expect(result.current.currentSessionId).toBe('sess-42');
      expect(defaultProps.setActiveMode).toHaveBeenCalledWith('research');
      expect(result.current.sessionStats.queries).toBe(2);
    });

    it('surfaces a toast when the session cannot be loaded', async () => {
      (api.getChatSession as any).mockRejectedValue(new Error('Not found'));

      const { result } = renderHook(() => useResearchState(defaultProps));
      await act(async () => {
        await result.current.loadSession('missing');
      });

      expect(defaultProps.addToast).toHaveBeenCalledWith('Not found', 'error');
      expect(result.current.currentSessionId).toBeNull();
    });
  });

  describe('deleteSession', () => {
    it('removes the session from the list and resets the active thread', async () => {
      (api.query as any).mockResolvedValue({
        content: 'Answer',
        citations: [],
        session_id: 'sess-del',
      });
      (api.deleteChatSession as any).mockResolvedValue({ status: 'deleted', id: 'sess-del' });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('question'));
      await act(async () => {
        await result.current.handleSend();
      });
      expect(result.current.currentSessionId).toBe('sess-del');

      await act(async () => {
        await result.current.deleteSession('sess-del');
      });

      expect(api.deleteChatSession).toHaveBeenCalledWith('sess-del');
      expect(result.current.currentSessionId).toBeNull();
      expect(result.current.messages).toEqual([]);
    });
  });

  describe('handleCitationUpdate', () => {
    it('updates citation status in allCitations', async () => {
      (api.query as any).mockResolvedValue({
        response: 'Answer',
        citations: [
          { text: 'Citation 1', source: 'doc.pdf', relevance_score: 0.9, chunk_index: 0 },
        ],
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('query'));
      await act(async () => {
        await result.current.handleSend();
      });

      const citationId = result.current.allCitations[0]?.id;
      if (citationId) {
        act(() => {
          result.current.handleCitationUpdate(citationId, 'approved', 'Good source');
        });
        const updated = result.current.allCitations.find((c: any) => c.id === citationId);
        expect(updated?.status).toBe('approved');
      }
    });
  });

  describe('handleClearSession', () => {
    it('resets messages, citations, session id, stats', async () => {
      (api.query as any).mockResolvedValue({
        content: 'Answer',
        citations: [],
        session_id: 'sess-clear',
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('test'));
      await act(async () => {
        await result.current.handleSend();
      });
      expect(result.current.currentSessionId).toBe('sess-clear');

      act(() => result.current.handleClearSession());

      expect(result.current.messages).toEqual([]);
      expect(result.current.allCitations).toEqual([]);
      expect(result.current.currentSessionId).toBeNull();
      expect(result.current.sessionStats).toEqual({
        queries: 0,
        citations: 0,
        approved: 0,
        rejected: 0,
        pending: 0,
      });
    });
  });

  describe('filteredCitations', () => {
    it('filters by citationFilter', async () => {
      (api.query as any).mockResolvedValue({
        response: 'Answer',
        citations: [
          { text: 'C1', source: 'a.pdf', relevance_score: 0.9, chunk_index: 0 },
          { text: 'C2', source: 'b.pdf', relevance_score: 0.8, chunk_index: 1 },
        ],
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('query'));
      await act(async () => {
        await result.current.handleSend();
      });

      // All citations should be pending initially
      expect(result.current.filteredCitations.length).toBe(result.current.allCitations.length);

      act(() => result.current.setCitationFilter('approved'));
      expect(result.current.filteredCitations.length).toBe(0);
    });
  });

  describe('batch actions', () => {
    it('handleBatchApprove sets all pending to approved', async () => {
      (api.query as any).mockResolvedValue({
        response: 'Answer',
        citations: [
          { text: 'C1', source: 'a.pdf', relevance_score: 0.9, chunk_index: 0 },
        ],
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('query'));
      await act(async () => {
        await result.current.handleSend();
      });

      act(() => result.current.handleBatchApprove());
      expect(result.current.allCitations.every((c: any) => c.status === 'approved')).toBe(true);
    });

    it('handleBatchReject sets all pending to rejected', async () => {
      (api.query as any).mockResolvedValue({
        response: 'Answer',
        citations: [
          { text: 'C1', source: 'a.pdf', relevance_score: 0.9, chunk_index: 0 },
        ],
      });

      const { result } = renderHook(() => useResearchState(defaultProps));
      act(() => result.current.setInputValue('query'));
      await act(async () => {
        await result.current.handleSend();
      });

      act(() => result.current.handleBatchReject());
      expect(result.current.allCitations.every((c: any) => c.status === 'rejected')).toBe(true);
    });
  });
});
