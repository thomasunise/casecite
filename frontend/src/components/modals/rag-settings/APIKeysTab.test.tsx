import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { APIKeysTab } from './APIKeysTab';
import type { RagSettings } from '../../../types';

vi.mock('../../../api/client', () => ({
  api: { request: vi.fn().mockResolvedValue({}) },
}));

function defaultProps(overrides: Record<string, any> = {}) {
  const local: RagSettings = {
    vectorDb: 'chroma',
    indexName: 'default',
    embeddingModel: 'text-embedding-3-small',
    dimensions: 1536,
    chunkSize: 512,
    chunkOverlap: 64,
    similarityThreshold: 0.7,
    topK: 10,
    enableReranking: true,
    hybridSearch: true,
    citationVerification: true,
    contextCompression: false,
    queryExpansion: false,
    sourceTracking: true,
    llmModel: 'gpt-5.5',
    temperature: 0.1,
    maxTokens: 4096,
  };
  return {
    local,
    setLocal: vi.fn(),
    showKeys: {} as Record<string, boolean>,
    setShowKeys: vi.fn(),
    apiKeys: { openai: '', anthropic: '', google: '', voyage: '', cohere: '' } as Record<string, string>,
    setApiKeys: vi.fn(),
    serverKeyStatus: {} as Record<string, boolean>,
    maskedKeys: {} as Record<string, string | null>,
    keyStatusError: false,
    refreshKeyStatus: vi.fn(async () => {}),
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    ...overrides,
  };
}

describe('APIKeysTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<APIKeysTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('displays the Bring Your Own Keys banner', () => {
    const { container } = render(<APIKeysTab {...defaultProps()} />);
    expect(container.textContent).toContain('Bring Your Own Keys');
  });

  it('shows all provider key fields', () => {
    const { container } = render(<APIKeysTab {...defaultProps()} />);
    expect(container.textContent).toContain('OpenAI API Key');
    expect(container.textContent).toContain('Anthropic API Key');
    expect(container.textContent).toContain('Google Gemini API Key');
    expect(container.textContent).toContain('Voyage AI Key');
    expect(container.textContent).toContain('Cohere API Key');
  });

  it('shows the key status section', () => {
    const { container } = render(<APIKeysTab {...defaultProps()} />);
    expect(container.textContent).toContain('Key Status');
  });

  it('has password inputs for api keys', () => {
    const { container } = render(<APIKeysTab {...defaultProps()} />);
    const passwordInputs = container.querySelectorAll('input[type="password"]');
    expect(passwordInputs.length).toBeGreaterThanOrEqual(5);
  });
});
