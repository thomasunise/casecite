import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { PromptsTab } from './PromptsTab';
import type { RagSettings } from '../../../types';

vi.mock('../../../utils/logger', () => ({
  default: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
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
    batchSize: 100,
    custom_system_prompt: null,
    custom_grounding_rules: null,
    custom_factual_prompt: null,
    custom_research_prompt: null,
    custom_case_prompt: null,
    custom_document_prompt: null,
    custom_compliance_prompt: null,
    custom_strategy_prompt: null,
  };
  return {
    local,
    setLocal: vi.fn(),
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    ...overrides,
  };
}

describe('PromptsTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the custom prompts banner', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container.textContent).toContain('Custom Prompts');
  });

  it('shows quick answer prompt section', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container.textContent).toContain('Quick Answer Prompt');
  });

  it('shows system prompt section', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container.textContent).toContain('System Prompt (Analytical Base)');
  });

  it('shows grounding rules section', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container.textContent).toContain('Grounding Rules');
  });

  it('shows the clear all button', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    expect(container.textContent).toContain('Clear All Custom Prompts');
  });

  it('has textarea elements for prompts', () => {
    const { container } = render(<PromptsTab {...defaultProps()} />);
    const textareas = container.querySelectorAll('textarea');
    expect(textareas.length).toBeGreaterThanOrEqual(3);
  });
});
