import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchHistoryList } from './SearchHistoryList';
import type { ChatSessionSummary } from '../../api/types';

vi.mock('./Icon', () => ({
  Icon: ({ name, ...rest }: any) => <span data-testid={`icon-${name}`} {...rest} />,
}));

const s = new Proxy({} as Record<string, string>, { get: (_, key) => String(key) });

function makeSession(overrides: Partial<ChatSessionSummary> = {}): ChatSessionSummary {
  return {
    id: 'sess-1',
    title: 'Qualified immunity research',
    created_at: '2026-07-01T10:00:00',
    updated_at: '2026-07-01T10:05:00',
    message_count: 4,
    ...overrides,
  };
}

function defaultProps(overrides: Record<string, any> = {}) {
  return {
    s,
    sessions: [] as ChatSessionSummary[],
    isLoading: false,
    currentSessionId: null as string | null,
    onSessionClick: vi.fn(),
    onDeleteSession: vi.fn(),
    onNewChat: vi.fn(),
    ...overrides,
  };
}

describe('SearchHistoryList', () => {
  it('renders without crashing', () => {
    const { container } = render(<SearchHistoryList {...defaultProps()} />);
    expect(container).toBeTruthy();
  });

  it('shows Conversations (0) when empty', () => {
    render(<SearchHistoryList {...defaultProps()} />);
    expect(screen.getByText('Conversations (0)')).toBeTruthy();
  });

  it('shows empty state when no sessions', () => {
    render(<SearchHistoryList {...defaultProps()} />);
    expect(screen.getByText('No conversations yet')).toBeTruthy();
    expect(screen.getByText('Your past conversations will appear here')).toBeTruthy();
  });

  it('shows loading state while sessions load', () => {
    render(<SearchHistoryList {...defaultProps({ isLoading: true })} />);
    expect(screen.getByText('Loading conversations...')).toBeTruthy();
  });

  it('renders session items when provided', () => {
    const sessions = [
      makeSession({ id: '1', title: 'Qualified immunity' }),
      makeSession({ id: '2', title: 'Breach of contract', message_count: 8 }),
    ];
    render(<SearchHistoryList {...defaultProps({ sessions })} />);
    expect(screen.getByText('Conversations (2)')).toBeTruthy();
    expect(screen.getByText('Qualified immunity')).toBeTruthy();
    expect(screen.getByText('Breach of contract')).toBeTruthy();
  });

  it('shows message count in meta', () => {
    const sessions = [makeSession({ message_count: 6 })];
    const { container } = render(<SearchHistoryList {...defaultProps({ sessions })} />);
    expect(container.textContent).toContain('6 messages');
  });

  it('clicking a session calls onSessionClick with its id', () => {
    const onSessionClick = vi.fn();
    const sessions = [makeSession({ id: 'sess-9', title: 'Open me' })];
    render(<SearchHistoryList {...defaultProps({ sessions, onSessionClick })} />);
    fireEvent.click(screen.getByText('Open me'));
    expect(onSessionClick).toHaveBeenCalledWith('sess-9');
  });

  it('clicking delete calls onDeleteSession without opening the session', () => {
    const onSessionClick = vi.fn();
    const onDeleteSession = vi.fn();
    const sessions = [makeSession({ id: 'sess-9', title: 'Delete me' })];
    render(
      <SearchHistoryList {...defaultProps({ sessions, onSessionClick, onDeleteSession })} />
    );
    fireEvent.click(screen.getByLabelText('Delete conversation Delete me'));
    expect(onDeleteSession).toHaveBeenCalledWith('sess-9');
    expect(onSessionClick).not.toHaveBeenCalled();
  });

  it('clicking New conversation calls onNewChat', () => {
    const onNewChat = vi.fn();
    render(<SearchHistoryList {...defaultProps({ onNewChat })} />);
    fireEvent.click(screen.getByText('New conversation'));
    expect(onNewChat).toHaveBeenCalled();
  });
});
