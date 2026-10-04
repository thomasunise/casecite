import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { RetrievalTab } from './RetrievalTab';
import type { RagSettings } from '../../../types';

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
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    ...overrides,
  };
}

describe('RetrievalTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows vector database selector', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('Vector Database');
  });

  it('shows index name input', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('Index Name');
  });

  it('shows top K results slider', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('Top K Results');
  });

  it('shows similarity threshold slider', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('Similarity Threshold');
  });

  it('shows chunk size and overlap sliders', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('Chunk Size');
    expect(container.textContent).toContain('Chunk Overlap');
  });

  it('lists vector database options', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    expect(container.textContent).toContain('ChromaDB');
    expect(container.textContent).toContain('Pinecone');
  });

  it('has range inputs for sliders', () => {
    const { container } = render(<RetrievalTab {...defaultProps()} />);
    const ranges = container.querySelectorAll('input[type="range"]');
    expect(ranges.length).toBe(4);
  });
});
