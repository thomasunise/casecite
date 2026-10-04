import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('../../utils/markdownUtils', () => ({
  cleanMarkdown: (text: string) => text.replace(/^#+\s*/, '').replace(/\*\*/g, ''),
}));

import JudgeBriefTab from './JudgeBriefTab';

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s: new Proxy({} as Record<string, string>, { get: (_, key) => String(key) }),
    judgeIntelProfile: {
      id: 'judge-1',
      name: 'John Roberts',
    },
    judgeBrief: null,
    judgeBriefLoading: false,
    generateJudgeBrief: vi.fn(),
    judgeMessages: [],
    setJudgeQueryInput: vi.fn(),
    judgeQueryLoading: false,
    judgeQueryIncludeDocs: false,
    clearJudgeConversation: vi.fn(),
    ...overrides,
  };
}

describe('JudgeBriefTab', () => {
  it('renders without crashing', () => {
    const { container } = render(<JudgeBriefTab {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows the brief title', () => {
    const { container } = render(<JudgeBriefTab {...defaultProps()} />);
    expect(container.textContent).toContain('Judicial Profile Brief');
  });

  it('shows placeholder when no brief generated', () => {
    const { container } = render(<JudgeBriefTab {...defaultProps()} />);
    expect(container.textContent).toContain('AI-Generated Intelligence Brief');
    expect(container.textContent).toContain('Generate Brief');
  });

  it('shows loading state when generating brief', () => {
    const { container } = render(
      <JudgeBriefTab {...defaultProps({ judgeBriefLoading: true })} />,
    );
    expect(container.textContent).toContain('Analyzing judge data');
  });

  it('renders brief content when available', () => {
    const brief = '## Judicial Philosophy\nThis judge is known for strict textualism.\n\n- Key point one\n- Key point two';
    const { container } = render(
      <JudgeBriefTab {...defaultProps({ judgeBrief: brief })} />,
    );
    expect(container.textContent).toContain('Judicial Philosophy');
    expect(container.textContent).toContain('strict textualism');
  });

  it('shows the ask section', () => {
    const { container } = render(<JudgeBriefTab {...defaultProps()} />);
    expect(container.textContent).toContain('Ask About This Judge');
  });

  it('shows query hints when there are no messages', () => {
    const { container } = render(<JudgeBriefTab {...defaultProps()} />);
    expect(container.textContent).toContain('Try asking:');
    expect(container.textContent).toContain('What is their judicial philosophy?');
  });

  it('fills the composer input when a hint is clicked', () => {
    const setJudgeQueryInput = vi.fn();
    const { getByText } = render(
      <JudgeBriefTab {...defaultProps({ setJudgeQueryInput })} />,
    );
    getByText('What is their judicial philosophy?').click();
    expect(setJudgeQueryInput).toHaveBeenCalledWith('What is their judicial philosophy?');
  });

  it('renders the conversation instead of hints once messages exist', () => {
    const { container } = render(
      <JudgeBriefTab {...defaultProps({
        judgeMessages: [
          { id: 1, type: 'user', content: 'How strict on suppression motions?' },
          { id: 2, type: 'assistant', content: 'Based on the record...' },
        ],
      })} />,
    );
    expect(container.textContent).toContain('How strict on suppression motions?');
    expect(container.textContent).toContain('Based on the record...');
    expect(container.textContent).not.toContain('Try asking:');
  });
});
