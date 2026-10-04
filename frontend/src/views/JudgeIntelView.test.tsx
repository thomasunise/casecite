import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithAppContext } from '../test/helpers';
import JudgeIntelView from './JudgeIntelView';

function defaultCtx(overrides: Record<string, any> = {}) {
  return {
    judgeIntelBuilding: false,
    judgeIntelBuildProgress: null,
    judgeIntelProfile: null,
    judgeIntelResults: [],
    judgeIntelSearch: '',
    setJudgeIntelSearch: vi.fn(),
    searchJudgesIntel: vi.fn(),
    judgeIntelLoading: false,
    judgeIntelOpinions: [],
    judgeIntelOpinionQuery: '',
    setJudgeIntelOpinionQuery: vi.fn(),
    queryJudgeOpinions: vi.fn(),
    selectedOpinion: null,
    setSelectedOpinion: vi.fn(),
    loadOpinionFullText: vi.fn(),
    judgeBrief: null,
    judgeBriefLoading: false,
    generateJudgeBrief: vi.fn(),
    judgeMessages: [],
    judgeQueryInput: '',
    setJudgeQueryInput: vi.fn(),
    judgeQueryLoading: false,
    queryJudgeContext: vi.fn(),
    judgeDocFilter: null,
    setJudgeDocFilter: vi.fn(),
    showJudgeDocSelector: false,
    setShowJudgeDocSelector: vi.fn(),
    buildJudgeIntel: vi.fn(),
    judgeIntelCached: [],
    isAuthenticated: true,
    ...overrides,
  };
}

describe('JudgeIntelView', () => {
  it('renders without crashing', () => {
    const { container } = renderWithAppContext(<JudgeIntelView />, defaultCtx());
    expect(container).toBeTruthy();
  });

  it('shows search input', () => {
    renderWithAppContext(<JudgeIntelView />, defaultCtx());
    const searchInput = screen.getByPlaceholderText(/judge|search/i);
    expect(searchInput).toBeInTheDocument();
  });
});
