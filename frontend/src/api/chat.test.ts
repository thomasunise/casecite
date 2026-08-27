import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => {
  const api = {
    request: vi.fn(),
    authFetch: vi.fn(),
  };
  return { api, API_BASE_URL: 'http://localhost:8000/api/v1' };
});

import { api } from './client';
import './chat';

describe('api/chat', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('registers query method on api object', () => {
    expect(typeof (api as any).query).toBe('function');
  });

  it('query sends POST to /chat with default options', async () => {
    (api.request as any).mockResolvedValue({ response: 'answer' });
    await (api as any).query('What is tort law?', 'research');
    expect(api.request).toHaveBeenCalledWith('/chat', {
      method: 'POST',
      // chat answers can read full opinions — well past the 30s default abort
      timeout: 180000,
      body: JSON.stringify({
        query: 'What is tort law?',
        mode: 'research',
        include_citations: true,
        // null = server decides per message whether authority helps
        include_case_law: null,
        case_law_limit: 5,
        include_documents: true,
        document_filter: null,
        session_id: null,
      }),
    });
  });

  it('query passes custom options correctly', async () => {
    (api.request as any).mockResolvedValue({ response: 'result' });
    await (api as any).query('test', 'analysis', {
      includeCaseLaw: false,
      caseLawLimit: 10,
      includeDocuments: false,
      documentFilter: 'contracts',
      sessionId: 'sess-77',
    });
    expect(api.request).toHaveBeenCalledWith('/chat', {
      method: 'POST',
      timeout: 180000,
      body: JSON.stringify({
        query: 'test',
        mode: 'analysis',
        include_citations: true,
        include_case_law: false,
        case_law_limit: 10,
        include_documents: false,
        document_filter: 'contracts',
        session_id: 'sess-77',
      }),
    });
  });

  it('query returns the response data', async () => {
    const expected = { response: 'Legal analysis', citations: [] };
    (api.request as any).mockResolvedValue(expected);
    const result = await (api as any).query('test', 'research');
    expect(result).toEqual(expected);
  });
});
