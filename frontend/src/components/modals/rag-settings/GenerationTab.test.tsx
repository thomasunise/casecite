import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { GenerationTab } from './GenerationTab';
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

describe('GenerationTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows LLM model selector', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    expect(container.textContent).toContain('LLM Model');
  });

  it('shows temperature slider', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    expect(container.textContent).toContain('Temperature');
  });

  it('shows max tokens slider', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    expect(container.textContent).toContain('Max Tokens');
  });

  it('lists model options from multiple providers', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    expect(container.textContent).toContain('GPT-5.5');
    expect(container.textContent).toContain('Claude Opus 4.8');
    expect(container.textContent).toContain('Gemini 3.1 Pro');
  });

  it('has range inputs for sliders', () => {
    const { container } = render(<GenerationTab {...defaultProps()} />);
    const ranges = container.querySelectorAll('input[type="range"]');
    expect(ranges.length).toBe(2);
  });
});
