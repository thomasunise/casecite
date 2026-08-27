import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { EmbeddingTab } from './EmbeddingTab';
import type { RagSettings } from '../../../types';

function defaultProps(overrides: Record<string, any> = {}) {
  const local: RagSettings = {
    vectorDb: 'chroma',
    indexName: 'default',
    embeddingModel: 'text-embedding-3-large',
    dimensions: 3072,
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
    batchSize: 100,
  };
  return {
    local,
    setLocal: vi.fn(),
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    ...overrides,
  };
}

describe('EmbeddingTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the embedding model selector', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Embedding Model');
  });

  it('shows embedding dimensions input', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Embedding Dimensions');
  });

  it('shows batch size input', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    expect(container.textContent).toContain('Batch Size');
  });

  it('has a select element for embedding model', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    const selects = container.querySelectorAll('select');
    expect(selects.length).toBe(1);
  });

  it('lists model options', () => {
    const { container } = render(<EmbeddingTab {...defaultProps()} />);
    expect(container.textContent).toContain('voyage-law-2');
    expect(container.textContent).toContain('text-embedding-3-large');
  });
});
