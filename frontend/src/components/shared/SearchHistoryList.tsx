import { Icon } from './Icon';
import { parseUtcDate } from '../../utils';
import type { ChatSessionSummary } from '../../api/types';

interface SearchHistoryListProps {
  s: Record<string, string>;
  sessions: ChatSessionSummary[];
  isLoading: boolean;
  currentSessionId: string | null;
  onSessionClick: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewChat: () => void;
}

function SearchHistoryList({ s, sessions, isLoading, currentSessionId, onSessionClick, onDeleteSession, onNewChat }: SearchHistoryListProps) {
  return (
    <div className={s.rightSection}>
      <h4 className={s.rightSectionTitle}>Conversations ({sessions.length})</h4>
      <button className={s.newChatBtn} onClick={onNewChat}>
        <Icon name="Plus" size={14} /> New conversation
      </button>
      {isLoading && sessions.length === 0 ? (
        <div className={s.emptyPanel}>
          <Icon name="Loader2" size={24} className={s.emptyPanelIcon} />
          <div>Loading conversations...</div>
        </div>
      ) : sessions.length === 0 ? (
        <div className={s.emptyPanel}>
          <Icon name="History" size={24} className={s.emptyPanelIcon} />
          <div>No conversations yet</div>
          <div className={s.emptyPanelDesc}>
            Your past conversations will appear here
          </div>
        </div>
      ) : (
        <div className={s.historyList}>
          {sessions.map((session: ChatSessionSummary) => (
            <div key={session.id} className={s.historyRow}>
              <button
                className={`${s.historyItem} ${session.id === currentSessionId ? s.historyItemActive : ''}`}
                onClick={() => onSessionClick(session.id)}
              >
                <Icon name="MessageSquare" size={14} className={s.iconGray400} />
                <div className={s.historyContent}>
                  <span className={s.historyQuery}>{session.title}</span>
                  <span className={s.historyMeta}>
                    {session.message_count} messages • {parseUtcDate(session.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </button>
              <button
                className={s.historyDeleteBtn}
                onClick={() => onDeleteSession(session.id)}
                title="Delete conversation"
                aria-label={`Delete conversation ${session.title}`}
              >
                <Icon name="Trash2" size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export { SearchHistoryList };
